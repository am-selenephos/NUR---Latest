"""HTTP-time validation, before decide() queues anything.

`_check_binding` proves the client saw what is currently stored — digest,
plan_version, call_version. It says nothing about whether what is stored is
itself still trustworthy: expired, written against a tool the registry no
longer serves at that version, or naming a handler that was never bound at
all. `_validate_before_queue` covers that, and `validate_arguments` covers the
one thing unique to EDIT — that the replacement payload is actually shaped
like a call the tool accepts, not an arbitrary dict.

Every rejection here must be provable as a *no-op*: the approval, the step,
the ledger and the outbox must all read exactly as they did before the
refused call.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers
from app.agentic.approvals import compute_call_version
from app.agentic.decisions import DecisionRefused, decide
from app.models.agentic import AgentApproval, AgentStep, AgentWorkflow
from app.tests.conftest import register_user

TOOL = "get_timeline"          # required: none — a valid {} edit target
UNBOUND_TOOL = "create_capsule"  # declared, deliberately never bound


@pytest.fixture(autouse=True)
def bound_handlers():
    # Not bind_durable_handlers(): registry.bind() is a permanent, global,
    # process-wide mutation with no reset between test files, and
    # test_draft_handlers.py asserts R2 tools stay unbound. Binding one here
    # would leak into that test if this file collects first.
    handlers.bind_read_only_handlers()
    handlers.bind_draft_handlers()


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


@dataclass(frozen=True)
class Seeded:
    workflow_id: uuid.UUID
    step_id: uuid.UUID
    approval_id: uuid.UUID
    argument_digest: str
    call_version: str


async def _seed(
    db, owner, *, tool_key=TOOL, tool_version="1", cost_ceiling_cents=0,
    expires_at=None, decision="PENDING",
) -> Seeded:
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING", plan_version=1
    )
    db.add(workflow)
    await db.flush()
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a",
        state="WAITING_APPROVAL", role="operator", tool_key=tool_key, tool_version=tool_version,
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
    )
    db.add(step)
    await db.flush()
    digest = "sha256:a"
    # Canonical and self-consistent with this row's own recorded tool_version —
    # a real drift scenario is the *registry's* current version disagreeing
    # with what this approval was written for, not the approval disagreeing
    # with itself.
    call_version = compute_call_version(1, tool_key, tool_version, digest)
    approval = AgentApproval(
        owner_user_id=owner, workflow_id=workflow.id, step_id=step.id,
        tool_key=tool_key, tool_version=tool_version, argument_digest=digest,
        rationale="r", risk_class="R0_READ_ONLY", decision=decision,
        plan_version=1, call_version=call_version,
        cost_ceiling_cents=cost_ceiling_cents, expires_at=expires_at,
    )
    db.add(approval)
    await db.flush()
    # Plain values, captured before commit: a rollback later in the test
    # expires every ORM-tracked attribute, and reloading one outside an
    # awaited context is exactly the "IO in an unexpected place" async
    # SQLAlchemy refuses to do.
    seeded = Seeded(
        workflow_id=workflow.id, step_id=step.id, approval_id=approval.id,
        argument_digest=digest, call_version=call_version,
    )
    await db.commit()
    return seeded


async def _snapshot(db, step_id, approval_id):
    approval_row = (
        await db.execute(
            text("SELECT decision, call_version FROM agent_approvals WHERE id = :a"),
            {"a": approval_id},
        )
    ).mappings().one()
    step_row = (
        await db.execute(
            text("SELECT state FROM agent_steps WHERE id = :s"), {"s": step_id}
        )
    ).mappings().one()
    events = (
        await db.execute(
            text("SELECT count(*) FROM agent_run_events WHERE step_id = :s"), {"s": step_id}
        )
    ).scalar()
    outbox = (
        await db.execute(
            text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"), {"s": step_id}
        )
    ).scalar()
    return approval_row["decision"], approval_row["call_version"], step_row["state"], events, outbox


@pytest.mark.asyncio
async def test_expired_approval_is_refused_and_mutates_nothing(scoped, owner):
    expired = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    seeded = await _seed(scoped, owner, expires_at=expired)
    before = await _snapshot(scoped, seeded.step_id, seeded.approval_id)

    with pytest.raises(DecisionRefused) as caught:
        await decide(
            scoped, owner_user_id=owner, approval_id=seeded.approval_id, decision="APPROVE",
            seen_digest=seeded.argument_digest, seen_plan_version=1,
            seen_call_version=seeded.call_version,
        )
    assert caught.value.status_code == 409
    assert "expired" in str(caught.value)
    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    assert await _snapshot(scoped, seeded.step_id, seeded.approval_id) == before


@pytest.mark.asyncio
async def test_registry_version_drift_is_refused_at_decision_time(scoped, owner):
    """The approval was written for a version the registry no longer serves —
    simulating drift between approval creation and decision without touching
    the planner or the registry itself."""
    seeded = await _seed(scoped, owner, tool_version="99")
    before = await _snapshot(scoped, seeded.step_id, seeded.approval_id)

    with pytest.raises(DecisionRefused) as caught:
        await decide(
            scoped, owner_user_id=owner, approval_id=seeded.approval_id, decision="APPROVE",
            seen_digest=seeded.argument_digest, seen_plan_version=1,
            seen_call_version=seeded.call_version,
        )
    assert caught.value.status_code == 409
    assert "registry now serves" in str(caught.value)
    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    assert await _snapshot(scoped, seeded.step_id, seeded.approval_id) == before


@pytest.mark.asyncio
async def test_unbound_tool_is_refused_and_mutates_nothing(scoped, owner):
    seeded = await _seed(scoped, owner, tool_key=UNBOUND_TOOL, tool_version="1")
    before = await _snapshot(scoped, seeded.step_id, seeded.approval_id)

    with pytest.raises(DecisionRefused) as caught:
        await decide(
            scoped, owner_user_id=owner, approval_id=seeded.approval_id, decision="APPROVE",
            seen_digest=seeded.argument_digest, seen_plan_version=1,
            seen_call_version=seeded.call_version,
        )
    assert caught.value.status_code == 409
    assert "no bound handler" in str(caught.value)
    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    assert await _snapshot(scoped, seeded.step_id, seeded.approval_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "edited,expected_fragment",
    [
        ({"limit": 5, "surprise": "field"}, "unknown field 'surprise'"),
        ({"limit": "not-an-int"}, "must be"),
    ],
)
async def test_invalid_edit_is_refused_and_mutates_nothing(scoped, owner, edited, expected_fragment):
    seeded = await _seed(scoped, owner)
    before = await _snapshot(scoped, seeded.step_id, seeded.approval_id)

    with pytest.raises(DecisionRefused) as caught:
        await decide(
            scoped, owner_user_id=owner, approval_id=seeded.approval_id, decision="EDIT",
            seen_digest=seeded.argument_digest, seen_plan_version=1,
            seen_call_version=seeded.call_version, edited_arguments=edited,
        )
    assert caught.value.status_code == 422
    assert expected_fragment in str(caught.value)
    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    assert await _snapshot(scoped, seeded.step_id, seeded.approval_id) == before


@pytest.mark.asyncio
async def test_missing_required_field_is_refused(scoped, owner):
    seeded = await _seed(scoped, owner, tool_key="create_draft_plan")
    before = await _snapshot(scoped, seeded.step_id, seeded.approval_id)

    with pytest.raises(DecisionRefused) as caught:
        await decide(
            scoped, owner_user_id=owner, approval_id=seeded.approval_id, decision="EDIT",
            seen_digest=seeded.argument_digest, seen_plan_version=1,
            seen_call_version=seeded.call_version, edited_arguments={},
        )
    assert caught.value.status_code == 422
    assert "missing required field 'title'" in str(caught.value)
    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    assert await _snapshot(scoped, seeded.step_id, seeded.approval_id) == before


@pytest.mark.asyncio
async def test_empty_edit_accepted_when_schema_permits(scoped, owner):
    """The contrast case: {} is not rejected on principle, only when the
    schema actually requires something it doesn't have."""
    seeded = await _seed(scoped, owner)  # get_timeline: no required fields

    result = await decide(
        scoped, owner_user_id=owner, approval_id=seeded.approval_id, decision="EDIT",
        seen_digest=seeded.argument_digest, seen_plan_version=1,
        seen_call_version=seeded.call_version, edited_arguments={},
    )
    await scoped.commit()
    assert result.step_state == "QUEUED"

    edited_row = (
        await scoped.execute(
            text("SELECT decision, edited_arguments FROM agent_approvals WHERE id = :a"),
            {"a": seeded.approval_id},
        )
    ).mappings().one()
    assert edited_row["decision"] == "EDITED"
    assert edited_row["edited_arguments"] == {}
