"""An owner approves through HTTP and the exact approved call reaches the handler.

The whole chain, no mocked seam: registered owner, real endpoint, real decision
transaction, committed outbox intent, real dispatcher, real worker coroutine,
real bound handler.
"""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import dispatcher, handlers
from app.agentic.approvals import compute_call_version
from app.agentic.enums import InitiativeLevel, RiskClass
from app.agentic.orchestrator import argument_digest
from app.models.agentic import AgentApproval, AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user
from app.workers import agentic_tasks

TOOL = "get_timeline"
ARGS = {"limit": 3}


@pytest.fixture(autouse=True)
def bound_handlers():
    handlers.bind_read_only_handlers()


@pytest.fixture()
async def owner(client) -> UUID:
    response, _e, _p = await register_user(client)
    assert response.status_code == 201
    return UUID(response.json()["id"])


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


async def _waiting_step_with_approval(db, owner: UUID, plan_version: int = 1):
    db.add(
        AgentPolicy(
            owner_user_id=owner,
            initiative_level=InitiativeLevel.INTERNAL.value,
            max_risk_class=RiskClass.R2_DURABLE_PRIVATE.value,
            permitted_tools=[TOOL],
            auto_run_tools=[TOOL],
        )
    )
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="TEST", title="approve me", objective="o",
        state="WAITING_APPROVAL", plan_version=plan_version,
    )
    db.add(workflow)
    await db.flush()
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a",
        state="WAITING_APPROVAL", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs=dict(ARGS),
    )
    db.add(step)
    await db.flush()

    digest = argument_digest(TOOL, "1", ARGS)
    approval = AgentApproval(
        owner_user_id=owner, workflow_id=workflow.id, step_id=step.id,
        tool_key=TOOL, tool_version="1", argument_digest=digest,
        redacted_arguments=dict(ARGS), rationale="please confirm",
        risk_class="R0_READ_ONLY", decision="PENDING",
        plan_version=plan_version,
        call_version=compute_call_version(plan_version, TOOL, "1", digest),
    )
    db.add(approval)
    await db.commit()
    return workflow, step, approval


def _csrf(c) -> dict:
    """The app issues a CSRF cookie on registration; state-changing routes
    require it echoed as a header."""
    return {"X-CSRF-Token": c.cookies.get("nur_csrf")}


def _body(approval, decision, **extra):
    return {
        "decision": decision,
        "seen_digest": approval.argument_digest,
        "seen_plan_version": approval.plan_version,
        "seen_call_version": approval.call_version,
        **extra,
    }


@pytest.mark.asyncio
async def test_approve_reaches_the_handler(client, session_for, owner):
    async with session_for() as db:
        workflow, step, approval = await _waiting_step_with_approval(db, owner)
        ids = (workflow.id, step.id, approval.id)

    response = await client.post(
        f"/api/v1/agentic/approvals/{ids[2]}/decide",
        json=_body(approval, "APPROVE"),
        headers=_csrf(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "APPROVED"
    assert response.json()["step_state"] == "QUEUED"
    assert response.json()["outbox_intent_id"]

    async with session_for() as check:
        assert (
            await check.execute(text("SELECT state FROM agent_steps WHERE id = :s"),
                                {"s": ids[1]})
        ).scalar_one() == "QUEUED"
        assert (
            await check.execute(
                text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
                {"s": ids[1]},
            )
        ).scalar() == 1

    published: list[tuple] = []
    async with session_for() as dispatch_db:
        result = await dispatcher.dispatch_once(
            dispatch_db, dispatcher_id="d1", publish=lambda *a: published.append(a)
        )
        assert len(result["sent"]) == 1
    assert len(published) == 1

    outcome = await agentic_tasks._execute_step(
        str(ids[1]), str(owner), str(ids[0]), None
    )
    assert outcome["executed"] is True, outcome
    assert outcome["step_state"] == "SUCCEEDED", outcome

    async with session_for() as final:
        assert (
            await final.execute(
                text(
                    "SELECT count(*) FROM agent_tool_calls "
                    "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                ),
                {"s": ids[1]},
            )
        ).scalar() == 1


@pytest.mark.asyncio
async def test_edit_executes_exactly_the_edited_payload(client, session_for, owner):
    async with session_for() as db:
        workflow, step, approval = await _waiting_step_with_approval(db, owner)
        step_id, workflow_id, approval_id = step.id, workflow.id, approval.id

    edited = {"limit": 7}
    response = await client.post(
        f"/api/v1/agentic/approvals/{approval_id}/decide",
        json=_body(approval, "EDIT", edited_arguments=edited),
        headers=_csrf(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "EDIT"

    async with session_for() as check:
        row = (
            await check.execute(
                text(
                    "SELECT decision, edited_arguments, argument_digest, call_version "
                    "FROM agent_approvals WHERE id = :a"
                ),
                {"a": approval_id},
            )
        ).mappings().one()
        assert row["decision"] == "EDITED"
        assert row["edited_arguments"] == edited
        # digest and call_version recomputed from the edit, not the original
        assert row["argument_digest"] == argument_digest(TOOL, "1", edited)
        assert row["call_version"] == compute_call_version(
            1, TOOL, "1", row["argument_digest"]
        )

    outcome = await agentic_tasks._execute_step(
        str(step_id), str(owner), str(workflow_id), None
    )
    assert outcome["executed"] is True, outcome


@pytest.mark.asyncio
async def test_reject_never_dispatches(client, session_for, owner):
    async with session_for() as db:
        workflow, step, approval = await _waiting_step_with_approval(db, owner)
        step_id, approval_id = step.id, approval.id

    response = await client.post(
        f"/api/v1/agentic/approvals/{approval_id}/decide",
        json=_body(approval, "REJECT"),
        headers=_csrf(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["step_state"] == "CANCELLED"
    assert response.json()["outbox_intent_id"] is None

    async with session_for() as check:
        assert (
            await check.execute(text("SELECT state FROM agent_steps WHERE id = :s"),
                                {"s": step_id})
        ).scalar_one() == "CANCELLED"
        assert (
            await check.execute(
                text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
                {"s": step_id},
            )
        ).scalar() == 0


@pytest.mark.asyncio
async def test_a_second_decision_is_409_and_creates_no_extra_intent(
    client, session_for, owner
):
    async with session_for() as db:
        workflow, step, approval = await _waiting_step_with_approval(db, owner)
        step_id, approval_id = step.id, approval.id

    first = await client.post(
        f"/api/v1/agentic/approvals/{approval_id}/decide",
        json=_body(approval, "APPROVE"),
        headers=_csrf(client),
    )
    assert first.status_code == 200
    second = await client.post(
        f"/api/v1/agentic/approvals/{approval_id}/decide",
        json=_body(approval, "APPROVE"),
        headers=_csrf(client),
    )
    assert second.status_code == 409, second.text

    async with session_for() as check:
        assert (
            await check.execute(
                text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
                {"s": step_id},
            )
        ).scalar() == 1


@pytest.mark.asyncio
async def test_a_replanned_workflow_refuses_an_identical_call(client, session_for, owner):
    """The case digest equality cannot catch: same arguments, successor plan."""
    async with session_for() as db:
        workflow, step, approval = await _waiting_step_with_approval(db, owner)
        workflow_id, approval_id = workflow.id, approval.id

    async with session_for() as replan:
        await replan.execute(
            text("UPDATE agent_workflows SET plan_version = 2 WHERE id = :w"),
            {"w": workflow_id},
        )
        await replan.commit()

    response = await client.post(
        f"/api/v1/agentic/approvals/{approval_id}/decide",
        json=_body(approval, "APPROVE"),
        headers=_csrf(client),
    )
    assert response.status_code == 409, response.text
    assert "re-planned" in response.json()["detail"]


@pytest.mark.asyncio
async def test_missing_binding_fields_are_rejected(client, session_for, owner):
    async with session_for() as db:
        workflow, step, approval = await _waiting_step_with_approval(db, owner)
        approval_id = approval.id

    response = await client.post(
        f"/api/v1/agentic/approvals/{approval_id}/decide",
        json={"decision": "APPROVE", "seen_digest": approval.argument_digest}, headers=_csrf(client),
    )
    assert response.status_code == 422, response.text
    missing = {e["loc"][-1] for e in response.json()["detail"]}
    assert {"seen_plan_version", "seen_call_version"} <= missing


@pytest.mark.asyncio
async def test_reject_marks_the_workflow_cancelled(client, session_for, owner):
    """A rejected workflow with nothing runnable left must not read RUNNING."""
    async with session_for() as db:
        workflow, step, approval = await _waiting_step_with_approval(db, owner)
        workflow_id, step_id, approval_id = workflow.id, step.id, approval.id

    response = await client.post(
        f"/api/v1/agentic/approvals/{approval_id}/decide",
        json=_body(approval, "REJECT"),
        headers=_csrf(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["step_state"] == "CANCELLED"
    assert response.json()["workflow_state"] == "CANCELLED"

    async with session_for() as check:
        assert (
            await check.execute(
                text("SELECT state FROM agent_workflows WHERE id = :w"), {"w": workflow_id}
            )
        ).scalar_one() == "CANCELLED"
        assert (
            await check.execute(
                text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
                {"s": step_id},
            )
        ).scalar() == 0


@pytest.mark.asyncio
async def test_a_stale_actionable_row_is_replaced_without_a_unique_violation(
    client, session_for, owner
):
    """Promotion before invalidation trips uq_agent_approval_one_actionable and
    aborts the transaction before the invalidation can run."""
    async with session_for() as db:
        workflow, step, approval = await _waiting_step_with_approval(db, owner)
        step_id, approval_id = step.id, approval.id
        # An older APPROVED row for the same step, as a prior decision would leave.
        await db.execute(
            text(
                "INSERT INTO agent_approvals (owner_user_id, workflow_id, step_id, tool_key, "
                "tool_version, argument_digest, rationale, risk_class, decision, "
                "plan_version, call_version) "
                "VALUES (:o, :w, :s, :t, '1', :d, 'older', 'R0_READ_ONLY', 'APPROVED', 1, :cv)"
            ),
            {
                "o": owner, "w": workflow.id, "s": step.id, "t": TOOL,
                "d": "sha256:" + "9" * 64, "cv": "cv:" + "9" * 64,
            },
        )
        await db.commit()

    response = await client.post(
        f"/api/v1/agentic/approvals/{approval_id}/decide",
        json=_body(approval, "APPROVE"),
        headers=_csrf(client),
    )
    assert response.status_code == 200, response.text

    async with session_for() as check:
        rows = (
            await check.execute(
                text(
                    "SELECT id, decision FROM agent_approvals WHERE step_id = :s ORDER BY decision"
                ),
                {"s": step_id},
            )
        ).mappings().all()
        actionable = [r for r in rows if r["decision"] in ("APPROVED", "EDITED")]
        assert len(actionable) == 1, rows
        assert actionable[0]["id"] == approval_id
        assert any(r["decision"] == "INVALIDATED" for r in rows), "history must survive"
        assert (
            await check.execute(
                text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
                {"s": step_id},
            )
        ).scalar() == 1


@pytest.mark.asyncio
async def test_the_tool_call_records_its_authorising_approval(client, session_for, owner):
    """A durable effect must be traceable to the consent that permitted it."""
    async with session_for() as db:
        workflow, step, approval = await _waiting_step_with_approval(db, owner)
        workflow_id, step_id, approval_id = workflow.id, step.id, approval.id

    await client.post(
        f"/api/v1/agentic/approvals/{approval_id}/decide",
        json=_body(approval, "APPROVE"),
        headers=_csrf(client),
    )
    await agentic_tasks._execute_step(str(step_id), str(owner), str(workflow_id), None)

    async with session_for() as check:
        row = (
            await check.execute(
                text(
                    "SELECT approval_id, argument_digest FROM agent_tool_calls "
                    "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                ),
                {"s": step_id},
            )
        ).mappings().one()
        assert row["approval_id"] == approval_id
        assert row["argument_digest"] == argument_digest(TOOL, "1", ARGS)
