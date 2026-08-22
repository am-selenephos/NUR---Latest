"""The whole loop, once per path, through production entry points only.

Every other file in this suite proves one mechanism. These six prove that the
mechanisms compose: from a step that exists to a workflow in a truthful terminal
state, with the evidence to show what happened, using the registered dispatcher
task, the registered execution task, real PostgreSQL and forced RLS.

Deliberately no shortcuts here: no `dispatch_once` by hand, no `_execute_step`
coroutine, no fixture that binds handlers the production processes would not have
bound. `_dispatch_and_run` is the only helper, and all it does is call the two
registered tasks in the order Beat and the broker would.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic.orchestrator import reclaim_expired_steps
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user
from app.workers import agentic_tasks

TOOL = "get_timeline"


@pytest.fixture()
async def owner(client) -> uuid.UUID:
    response, _e, _p = await register_user(client)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@pytest.fixture()
def session_for(app_engine, owner):
    maker = async_sessionmaker(app_engine, expire_on_commit=False)

    def make():
        class Scoped:
            async def __aenter__(self):
                self.db = maker()
                await self.db.__aenter__()
                await self.db.execute(
                    text("SELECT set_config('app.current_user_id', :o, false)"),
                    {"o": str(owner)},
                )
                return self.db

            async def __aexit__(self, *exc):
                await self.db.__aexit__(*exc)

        return Scoped()

    return make


async def _apply(task, args):
    """Enter a registered task the way a prefork worker does."""
    import app.db.session as dbs

    if dbs._engine is not None:
        await dbs._engine.dispose()
        dbs._engine = None
        dbs._sessionmaker = None
    return await asyncio.to_thread(lambda: task.apply(args=args))


async def _dispatch_and_run(monkeypatch, owner) -> list[tuple]:
    """One dispatcher pass, then the execution task for whatever it published.

    Stands in for the broker hop only — the claim, the publish decision, the
    fencing and the execution are all the production code paths.
    `test_real_broker_e2e_db.py` covers the hop itself with a real worker.
    """
    published: list[tuple] = []
    monkeypatch.setattr(
        agentic_tasks.execute_agentic_step_task, "delay",
        lambda *args: published.append(args),
    )
    result = await _apply(agentic_tasks.dispatch_agentic_intents_task, [50])
    assert result.successful(), result.traceback

    for step_id, owner_id, workflow_id, traceparent in published:
        if uuid.UUID(owner_id) != owner:
            continue  # another test's work in the same shared database
        outcome = await _apply(
            agentic_tasks.execute_agentic_step_task,
            [step_id, owner_id, workflow_id, traceparent],
        )
        assert outcome.successful(), outcome.traceback
    return [p for p in published if uuid.UUID(p[1]) == owner]


async def _seed(db, owner, *, auto_run: bool, key="a", tool=TOOL, arguments=None):
    db.add(
        AgentPolicy(
            owner_user_id=owner, initiative_level="INTERNAL",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=[tool], auto_run_tools=[tool] if auto_run else [],
        )
    )
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="slice", objective="o", state="RUNNING"
    )
    db.add(workflow)
    await db.flush()
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key=key,
        state="QUEUED", role="operator", tool_key=tool, tool_version="1",
        risk_class="R0_READ_ONLY",
        input_refs=arguments if arguments is not None else {"limit": 3},
        depends_on=[],
    )
    db.add(step)
    await db.flush()
    await db.execute(
        text(
            "INSERT INTO agent_dispatch_outbox "
            "(owner_user_id, workflow_id, step_id, dispatch_key, state) "
            "VALUES (:o, :w, :s, :k, 'RETRYABLE')"
        ),
        {"o": owner, "w": workflow.id, "s": step.id, "k": f"{step.id}:slice"},
    )
    await db.commit()
    return workflow.id, step.id


async def _states(db, workflow_id, step_id) -> dict:
    step = (
        await db.execute(
            text("SELECT state, verification_verdict FROM agent_steps WHERE id = :s"),
            {"s": step_id},
        )
    ).mappings().one()
    workflow = (
        await db.execute(
            text("SELECT state FROM agent_workflows WHERE id = :w"), {"w": workflow_id}
        )
    ).scalar_one()
    calls = (
        await db.execute(
            text(
                "SELECT outcome, approval_id, redacted_arguments FROM agent_tool_calls "
                "WHERE step_id = :s"
            ),
            {"s": step_id},
        )
    ).mappings().all()
    events = (
        await db.execute(
            text(
                "SELECT event_type FROM agent_run_events "
                "WHERE workflow_id = :w ORDER BY sequence"
            ),
            {"w": workflow_id},
        )
    ).scalars().all()
    learning = (
        await db.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM learning_signals "
                " WHERE idempotency_key = :learning_key) AS signals, "
                "(SELECT count(*) FROM memory_candidates "
                " WHERE source_object_ids->>'agent_step_id' = :step) AS memories, "
                "(SELECT count(*) FROM semantic_claims "
                " WHERE subject_ref = :subject_ref) AS claims, "
                "(SELECT count(*) FROM why_changed_records "
                " WHERE entity_id = :step) AS changes"
            ),
            {
                "learning_key": f"agent_step:{step_id}:verification",
                "step": str(step_id),
                "subject_ref": f"agent_step:{step_id}",
            },
        )
    ).mappings().one()
    return {
        "step": step["state"], "verdict": step["verification_verdict"],
        "workflow": workflow, "calls": calls, "events": events,
        "learning": dict(learning),
    }


async def _card(db, step_id):
    return (
        await db.execute(
            text(
                "SELECT id, argument_digest, plan_version, call_version "
                "FROM agent_approvals WHERE step_id = :s AND decision = 'PENDING'"
            ),
            {"s": step_id},
        )
    ).mappings().one()


async def _decide_over_http(client, owner, card, decision, **extra) -> dict:
    """The owner's decision through the real HTTP route, CSRF and all."""
    csrf = client.cookies.get("nur_csrf")
    response = await client.post(
        f"/api/v1/agentic/approvals/{card['id']}/decide",
        json={
            "decision": decision,
            "seen_digest": card["argument_digest"],
            "seen_plan_version": card["plan_version"],
            "seen_call_version": card["call_version"],
            **extra,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── A. auto-run ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slice_a_auto_run(session_for, owner, monkeypatch):
    """queue → dispatcher → execution task → handler → verification → SUCCEEDED,
    with evidence, and a workflow that agrees."""
    async with session_for() as db:
        workflow_id, step_id = await _seed(db, owner, auto_run=True)

    await _dispatch_and_run(monkeypatch, owner)

    async with session_for() as check:
        state = await _states(check, workflow_id, step_id)
    assert state["step"] == "SUCCEEDED", state
    assert state["verdict"] == "PASS", state
    assert state["workflow"] == "SUCCEEDED", state
    succeeded = [c for c in state["calls"] if c["outcome"] == "SUCCEEDED"]
    assert len(succeeded) == 1, state["calls"]
    assert succeeded[0]["approval_id"] is None, "auto-run cited an approval"
    assert "STEP_EXECUTED" in state["events"]
    assert "STEP_VERIFIED" in state["events"]
    assert state["learning"] == {
        "signals": 1,
        "memories": 1,
        "claims": 1,
        "changes": 1,
    }


# ── B. approval ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slice_b_approval(session_for, owner, client, monkeypatch):
    """pause → owner reads the card over HTTP → APPROVE → outbox → dispatcher →
    worker → exactly the authorised payload → linked tool call → terminal."""
    async with session_for() as db:
        workflow_id, step_id = await _seed(db, owner, auto_run=False)

    await _dispatch_and_run(monkeypatch, owner)

    async with session_for() as check:
        state = await _states(check, workflow_id, step_id)
        assert state["step"] == "WAITING_APPROVAL", state
        assert state["workflow"] == "WAITING_APPROVAL", state
        card = await _card(check, step_id)

    # The owner sees it in their own inbox, over HTTP.
    listing = await client.get("/api/v1/agentic/approvals")
    assert listing.status_code == 200, listing.text
    assert str(card["id"]) in {row["id"] for row in listing.json()["approvals"]}

    body = await _decide_over_http(client, owner, card, "APPROVE")
    assert body["step_state"] == "QUEUED"
    assert body["outbox_intent_id"]

    await _dispatch_and_run(monkeypatch, owner)

    async with session_for() as check:
        state = await _states(check, workflow_id, step_id)
    assert state["step"] == "SUCCEEDED", state
    assert state["workflow"] == "SUCCEEDED", state
    succeeded = [c for c in state["calls"] if c["outcome"] == "SUCCEEDED"]
    assert len(succeeded) == 1, state["calls"]
    assert succeeded[0]["approval_id"] == card["id"], (
        "the durable effect is not traceable to the consent that authorised it"
    )
    assert succeeded[0]["redacted_arguments"] == {"limit": 3}, (
        "something other than the approved payload executed"
    )


# ── C. edit ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slice_c_edit(session_for, owner, client, monkeypatch):
    """EDIT → validated canonical payload → only the edited arguments run."""
    async with session_for() as db:
        workflow_id, step_id = await _seed(db, owner, auto_run=False)

    await _dispatch_and_run(monkeypatch, owner)
    async with session_for() as check:
        card = await _card(check, step_id)

    body = await _decide_over_http(
        client, owner, card, "EDIT", edited_arguments={"limit": 7}
    )
    assert body["step_state"] == "QUEUED"

    async with session_for() as check:
        edited = (
            await check.execute(
                text(
                    "SELECT decision, edited_arguments, argument_digest, call_version "
                    "FROM agent_approvals WHERE id = :a"
                ),
                {"a": card["id"]},
            )
        ).mappings().one()
    assert edited["decision"] == "EDITED"
    assert edited["edited_arguments"] == {"limit": 7}
    # The binding was recomputed: an edit is consent to something different.
    assert edited["argument_digest"] != card["argument_digest"]
    assert edited["call_version"] != card["call_version"]

    await _dispatch_and_run(monkeypatch, owner)

    async with session_for() as check:
        state = await _states(check, workflow_id, step_id)
    assert state["step"] == "SUCCEEDED", state
    succeeded = [c for c in state["calls"] if c["outcome"] == "SUCCEEDED"]
    assert len(succeeded) == 1, state["calls"]
    assert succeeded[0]["redacted_arguments"] == {"limit": 7}, (
        "the original payload ran instead of the owner's edit"
    )
    assert succeeded[0]["approval_id"] == card["id"]


# ── D. reject ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slice_d_reject(session_for, owner, client, monkeypatch):
    """REJECT → no new intent, nothing executes, and the workflow says so."""
    async with session_for() as db:
        workflow_id, step_id = await _seed(db, owner, auto_run=False)

    await _dispatch_and_run(monkeypatch, owner)
    async with session_for() as check:
        card = await _card(check, step_id)
        intents_before = (
            await check.execute(
                text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
                {"s": step_id},
            )
        ).scalar_one()

    body = await _decide_over_http(client, owner, card, "REJECT", note="not now")
    assert body["step_state"] == "CANCELLED"
    assert body["outbox_intent_id"] is None, "a rejection queued work"

    async with session_for() as check:
        intents_after = (
            await check.execute(
                text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
                {"s": step_id},
            )
        ).scalar_one()
        state = await _states(check, workflow_id, step_id)

    assert intents_after == intents_before, "a rejection created a dispatch intent"
    assert state["step"] == "CANCELLED", state
    assert state["workflow"] == "CANCELLED", (
        "a workflow with nothing runnable left still reads as in progress"
    )
    assert not [c for c in state["calls"] if c["outcome"] == "SUCCEEDED"], (
        "a rejected step executed anyway"
    )
    assert "APPROVAL_REJECTED" in state["events"]


# ── E. dependant ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slice_e_dependant(session_for, owner, monkeypatch):
    """parent SUCCEEDS → child BLOCKED → READY → QUEUED with a durable intent →
    a separate task execution → both succeed → workflow succeeds."""
    async with session_for() as db:
        db.add(
            AgentPolicy(
                owner_user_id=owner, initiative_level="INTERNAL",
                max_risk_class="R2_DURABLE_PRIVATE",
                permitted_tools=[TOOL], auto_run_tools=[TOOL],
            )
        )
        workflow = AgentWorkflow(
            owner_user_id=owner, kind="T", title="dep", objective="o", state="RUNNING"
        )
        db.add(workflow)
        await db.flush()
        parent = AgentStep(
            owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="p",
            state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
            risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
        )
        child = AgentStep(
            owner_user_id=owner, workflow_id=workflow.id, ordinal=2, key="c",
            state="BLOCKED", role="operator", tool_key=TOOL, tool_version="1",
            risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=["p"],
        )
        db.add_all([parent, child])
        await db.flush()
        await db.execute(
            text(
                "INSERT INTO agent_dispatch_outbox "
                "(owner_user_id, workflow_id, step_id, dispatch_key, state) "
                "VALUES (:o, :w, :s, :k, 'RETRYABLE')"
            ),
            {"o": owner, "w": workflow.id, "s": parent.id, "k": f"{parent.id}:slice"},
        )
        await db.commit()
        workflow_id, parent_id, child_id = workflow.id, parent.id, child.id

    # Parent runs; the runtime promotes and queues the child with its own intent.
    await _dispatch_and_run(monkeypatch, owner)

    async with session_for() as check:
        assert (
            await check.execute(
                text("SELECT state FROM agent_steps WHERE id = :s"), {"s": parent_id}
            )
        ).scalar_one() == "SUCCEEDED"
        child_state = (
            await check.execute(
                text("SELECT state FROM agent_steps WHERE id = :s"), {"s": child_id}
            )
        ).scalar_one()
        assert child_state == "QUEUED", f"the child was left {child_state}"
        assert (
            await check.execute(
                text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
                {"s": child_id},
            )
        ).scalar_one() == 1, "the child has no durable intent"

    # A second dispatcher pass carries the child, as a separate execution.
    await _dispatch_and_run(monkeypatch, owner)

    async with session_for() as check:
        state = await _states(check, workflow_id, child_id)
        assert state["step"] == "SUCCEEDED", state
        assert state["workflow"] == "SUCCEEDED", state
        for step_id in (parent_id, child_id):
            calls = (
                await check.execute(
                    text(
                        "SELECT count(*) FROM agent_tool_calls "
                        "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                    ),
                    {"s": step_id},
                )
            ).scalar_one()
            assert calls == 1, f"step {step_id} ran {calls} times"


# ── F. crash and recovery ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slice_f_crash_recovery(session_for, owner, monkeypatch):
    """A claimed execution dies → lease expires → recovery reclaims and re-queues
    → the dispatcher redelivers → the stale attempt is fenced → one result."""
    async with session_for() as db:
        workflow_id, step_id = await _seed(db, owner, auto_run=True)

    # A worker claims and dies: RUNNING, leased, never completed.
    async with session_for() as crashed:
        from app.agentic.orchestrator import claim_step

        dead = await claim_step(
            crashed, owner_user_id=owner, step_id=step_id, worker_id="crashed"
        )
        assert dead.claimed
        await crashed.commit()
        dead_token = dead.execution_attempt

        await crashed.execute(
            text(
                "UPDATE agent_steps SET lease_expires_at = now() - interval '1 minute' "
                "WHERE id = :s"
            ),
            {"s": step_id},
        )
        await crashed.commit()

    # Recovery through the registered task.
    result = await _apply(agentic_tasks.recover_agentic_steps_task, [50])
    assert result.successful(), result.traceback
    outcome = result.get()
    assert str(step_id) in outcome["reclaimed"], outcome
    assert str(step_id) in outcome["requeued"], outcome

    async with session_for() as check:
        row = (
            await check.execute(
                text("SELECT state, execution_attempt FROM agent_steps WHERE id = :s"),
                {"s": step_id},
            )
        ).mappings().one()
        assert row["state"] == "QUEUED"
        assert row["execution_attempt"] != dead_token, "the dead attempt was not fenced"

    # Redelivery carries it to completion.
    await _dispatch_and_run(monkeypatch, owner)

    async with session_for() as check:
        state = await _states(check, workflow_id, step_id)
        assert state["step"] == "SUCCEEDED", state
        assert state["workflow"] == "SUCCEEDED", state
        succeeded = [c for c in state["calls"] if c["outcome"] == "SUCCEEDED"]
        assert len(succeeded) == 1, (
            f"crash recovery produced {len(succeeded)} durable effects"
        )

    # Nothing left holding a lease, and nothing for a later sweep to find.
    async with session_for() as sweep:
        again = await reclaim_expired_steps(sweep, limit=50)
        await sweep.commit()
    assert step_id not in {r.step_id for r in again}, (
        "a completed step is still reclaimable"
    )
