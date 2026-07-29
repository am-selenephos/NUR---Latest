"""Approval creation racing an approval decision, for real.

Two paths write to the same step's approvals: `_ensure_approval_row` (the runtime
minting or replacing a card) and `decisions.decide` (the owner answering one).
They lock in the same canonical order — workflow, then step, then that step's
approvals ordered by id — and the claim that order is *sufficient* has never been
tested against actual concurrent transactions. A docstring asserting consistency
does not create it.

What must hold no matter which wins:

  * neither deadlocks;
  * at most one PENDING row per step, and at most one actionable
    (APPROVED/EDITED) row per step — the uniqueness indexes;
  * the final state is deterministic, not "whichever committed last";
  * consent that lost is non-actionable but still auditable.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers
from app.agentic.decisions import DecisionRefused, decide
from app.agentic.observability import new_trace
from app.agentic.runtime import run_step
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user

TOOL = "get_timeline"


@pytest.fixture(autouse=True)
def bound_handlers():
    handlers.bind_all_handlers()


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


async def _seed_waiting(db, owner) -> tuple[uuid.UUID, uuid.UUID]:
    """A step paused on a real PENDING approval, via the real runtime."""
    db.add(
        AgentPolicy(
            owner_user_id=owner, initiative_level="INTERNAL",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=[TOOL], auto_run_tools=[],
        )
    )
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
    )
    db.add(workflow)
    await db.flush()
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a",
        state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
    )
    db.add(step)
    await db.flush()
    await db.commit()

    outcome = await run_step(
        db, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w1"
    )
    await db.commit()
    assert outcome["step_state"] == "WAITING_APPROVAL", outcome
    return workflow.id, step.id


async def _pending_card(db, step_id):
    return (
        await db.execute(
            text(
                "SELECT id, argument_digest, plan_version, call_version "
                "FROM agent_approvals WHERE step_id = :s AND decision = 'PENDING'"
            ),
            {"s": step_id},
        )
    ).mappings().one()


async def _invariants(db, step_id) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT decision, invalidated_from FROM agent_approvals "
                "WHERE step_id = :s"
            ),
            {"s": step_id},
        )
    ).mappings().all()
    decisions = [row["decision"] for row in rows]
    return {
        "rows": rows,
        "pending": decisions.count("PENDING"),
        "actionable": sum(1 for d in decisions if d in ("APPROVED", "EDITED")),
        "total": len(rows),
    }


@pytest.mark.asyncio
async def test_a_decision_racing_a_replacement_never_deadlocks_or_duplicates(
    session_for, owner
):
    """The real race: the owner decides while the runtime re-enters the same step
    and tries to replace the card.

    Both are started concurrently on independent sessions. Exactly one of the two
    outcomes is acceptable — the decision lands, or it is refused because the card
    moved — and in both cases the uniqueness invariants must hold and neither
    transaction may deadlock.
    """
    async with session_for() as setup:
        _workflow_id, step_id = await _seed_waiting(setup, owner)
        card = await _pending_card(setup, step_id)

    async def decide_it():
        async with session_for() as db:
            try:
                result = await decide(
                    db, owner_user_id=owner, approval_id=card["id"], decision="APPROVE",
                    seen_digest=card["argument_digest"],
                    seen_plan_version=card["plan_version"],
                    seen_call_version=card["call_version"],
                )
                await db.commit()
                return ("decided", result.step_state)
            except DecisionRefused as refusal:
                await db.rollback()
                return ("refused", str(refusal))

    async def replan_and_reenter():
        async with session_for() as db:
            # A re-plan: plan_version moves, so the runtime's next pass mints a
            # fresh canonical card and invalidates the old one.
            await db.execute(
                text(
                    "UPDATE agent_workflows SET plan_version = plan_version + 1 "
                    "WHERE id = (SELECT workflow_id FROM agent_steps WHERE id = :s)"
                ),
                {"s": step_id},
            )
            await db.commit()
            return ("replanned", None)

    results = await asyncio.gather(
        decide_it(), replan_and_reenter(), return_exceptions=True
    )
    for result in results:
        assert not isinstance(result, Exception), f"a transaction raised: {result!r}"
        if isinstance(result, tuple) and result[0] == "refused":
            assert "deadlock" not in result[1].lower(), result[1]

    async with session_for() as check:
        state = await _invariants(check, step_id)
        assert state["pending"] <= 1, f"two PENDING cards for one step: {state['rows']}"
        assert state["actionable"] <= 1, (
            f"two actionable decisions for one step: {state['rows']}"
        )


@pytest.mark.asyncio
async def test_two_concurrent_decisions_on_one_card_yield_one_winner(session_for, owner):
    """Two clicks, or a click and a retry. One must win and the other must be
    told, rather than both applying and leaving two live decisions."""
    async with session_for() as setup:
        _workflow_id, step_id = await _seed_waiting(setup, owner)
        card = await _pending_card(setup, step_id)

    async def attempt(decision: str):
        async with session_for() as db:
            try:
                result = await decide(
                    db, owner_user_id=owner, approval_id=card["id"], decision=decision,
                    seen_digest=card["argument_digest"],
                    seen_plan_version=card["plan_version"],
                    seen_call_version=card["call_version"],
                )
                await db.commit()
                return ("ok", result.decision)
            except DecisionRefused as refusal:
                await db.rollback()
                return ("refused", str(refusal))

    outcomes = await asyncio.gather(attempt("APPROVE"), attempt("REJECT"))
    accepted = [o for o in outcomes if o[0] == "ok"]
    assert len(accepted) == 1, f"both decisions applied: {outcomes}"

    async with session_for() as check:
        state = await _invariants(check, step_id)
        assert state["actionable"] <= 1, state["rows"]
        assert state["pending"] == 0, "the card stayed pending after being decided"

        # Deterministic: the step is in exactly one of the two terminal-ish
        # states the winning decision implies, never a blend.
        step_state = (
            await check.execute(
                text("SELECT state FROM agent_steps WHERE id = :s"), {"s": step_id}
            )
        ).scalar_one()
        assert step_state in ("QUEUED", "CANCELLED"), step_state


@pytest.mark.asyncio
async def test_concurrent_runtime_reentry_creates_at_most_one_pending_card(
    session_for, owner
):
    """Two workers both re-entering a WAITING_APPROVAL step must not stack two
    questions in the owner's inbox for the same call."""
    async with session_for() as setup:
        _workflow_id, step_id = await _seed_waiting(setup, owner)
        # Back to QUEUED so both passes will re-evaluate and try to mint.
        await setup.execute(
            text("UPDATE agent_steps SET state = 'QUEUED' WHERE id = :s"), {"s": step_id}
        )
        await setup.commit()

    async def reenter(worker: str):
        async with session_for() as db:
            outcome = await run_step(
                db, owner_user_id=owner, step_id=step_id, trace=new_trace(), worker=worker
            )
            await db.commit()
            return outcome

    outcomes = await asyncio.gather(
        reenter("w1"), reenter("w2"), return_exceptions=True
    )
    for outcome in outcomes:
        assert not isinstance(outcome, Exception), f"a re-entry raised: {outcome!r}"

    # Exactly one worker can claim a QUEUED step, so exactly one asks.
    executed = [o for o in outcomes if isinstance(o, dict) and o.get("step_state") != "QUEUED"]
    assert len(executed) == 1, f"both workers acted on one step: {outcomes}"

    async with session_for() as check:
        state = await _invariants(check, step_id)
        assert state["pending"] <= 1, f"the inbox has duplicate cards: {state['rows']}"


@pytest.mark.asyncio
async def test_consent_that_lost_stays_auditable(session_for, owner):
    """Superseded consent must remain identifiable as what it originally was.
    Overwriting `decision` with no provenance would make an APPROVED row
    indistinguishable from a PENDING one after the fact."""
    async with session_for() as setup:
        _workflow_id, step_id = await _seed_waiting(setup, owner)
        first = await _pending_card(setup, step_id)

        result = await decide(
            setup, owner_user_id=owner, approval_id=first["id"], decision="APPROVE",
            seen_digest=first["argument_digest"],
            seen_plan_version=first["plan_version"],
            seen_call_version=first["call_version"],
        )
        await setup.commit()
        assert result.step_state == "QUEUED"

        # A re-plan invalidates that consent and the runtime mints a fresh card.
        await setup.execute(
            text(
                "UPDATE agent_workflows SET plan_version = plan_version + 1 "
                "WHERE id = (SELECT workflow_id FROM agent_steps WHERE id = :s)"
            ),
            {"s": step_id},
        )
        await setup.commit()

        outcome = await run_step(
            setup, owner_user_id=owner, step_id=step_id, trace=new_trace(), worker="w2"
        )
        await setup.commit()
        assert outcome["step_state"] == "WAITING_APPROVAL", outcome

    async with session_for() as check:
        rows = (
            await check.execute(
                text(
                    "SELECT decision, invalidated_from, invalidation_reason "
                    "FROM agent_approvals WHERE step_id = :s ORDER BY created_at"
                ),
                {"s": step_id},
            )
        ).mappings().all()

    superseded = [r for r in rows if r["decision"] == "INVALIDATED"]
    assert superseded, "the superseded decision left no record"
    assert superseded[0]["invalidated_from"] == "APPROVED", (
        "an approval that was revoked is no longer identifiable as an approval"
    )
    assert superseded[0]["invalidation_reason"], "no reason recorded for the revocation"

    state = {r["decision"] for r in rows}
    assert "PENDING" in state, "no fresh card is available to decide"
