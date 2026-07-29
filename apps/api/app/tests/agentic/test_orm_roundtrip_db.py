"""ORM insert-and-reload against PostgreSQL as the constrained app role.

Metadata comparison cannot prove a mapper issues valid SQL; only running it can.
AgentToolCall mapped two columns its table lacks, and every SELECT through that
mapper would have raised UndefinedColumn while every metadata assertion passed.

These use the harness the suite already has: `register_user` creates the owner
through the real registration endpoint, and `app_engine` connects as nur_app so
forced RLS is in effect. A skip here is a failure — the database is an autouse
requirement of this suite.
"""

import datetime as dt
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic.policy import Decision, evaluate
from app.agentic.policy_store import load_policy
from app.agentic.registry import contract
from app.models.agentic import (
    AgentApproval,
    AgentDispatchOutbox,
    AgentPolicy,
    AgentStep,
    AgentToolCall,
    AgentWorkflow,
)
from app.tests.conftest import register_user


@pytest.fixture()
async def owner(client) -> UUID:
    response, _email, _password = await register_user(client)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


@pytest.fixture()
async def scoped(app_engine, owner):
    """A session as nur_app with the owner's RLS context set."""
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        yield db


async def _workflow(db, owner: UUID, *, plan_version: int = 1) -> AgentWorkflow:
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="TEST", title="round trip",
        objective="prove the mapper", state="RUNNING", plan_version=plan_version,
    )
    db.add(workflow)
    await db.flush()
    return workflow


@pytest.mark.asyncio
async def test_agent_policy_roundtrip_and_decisions(scoped, owner):
    scoped.add(
        AgentPolicy(
            owner_user_id=owner,
            initiative_level="INTERNAL",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=["get_timeline", "create_draft_plan"],
            auto_run_tools=["get_timeline"],
        )
    )
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    reloaded = (
        await scoped.execute(select(AgentPolicy).where(AgentPolicy.owner_user_id == owner))
    ).scalar_one()
    assert reloaded.permitted_tools == ["get_timeline", "create_draft_plan"]
    assert reloaded.auto_run_tools == ["get_timeline"]

    policy = await load_policy(scoped, owner_user_id=owner)
    assert policy.permitted_tools == frozenset({"get_timeline", "create_draft_plan"})
    assert policy.auto_run_tools == frozenset({"get_timeline"})
    assert policy.granted_capabilities == frozenset({"read_timeline", "draft_plans"})

    assert evaluate(contract("get_timeline"), policy).decision is Decision.ALLOW
    assert evaluate(contract("create_draft_plan"), policy).decision is Decision.REQUIRE_APPROVAL
    assert evaluate(contract("get_insight"), policy).decision is Decision.DENY


@pytest.mark.asyncio
async def test_workflow_and_step_roundtrip(scoped, owner):
    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="WAITING_APPROVAL", role="operator", tool_key="get_timeline",
        tool_version="1", risk_class="R0_READ_ONLY", input_refs={"limit": 5},
    )
    scoped.add(step)
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    back = (await scoped.execute(select(AgentStep).where(AgentStep.id == step.id))).scalar_one()
    assert back.key == "s1"
    assert back.input_refs == {"limit": 5}
    assert back.workflow_id == workflow.id


@pytest.mark.asyncio
async def test_agent_approval_roundtrip_with_call_version(scoped, owner):
    workflow = await _workflow(scoped, owner, plan_version=2)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="WAITING_APPROVAL", role="operator",
    )
    scoped.add(step)
    await scoped.flush()

    approval = AgentApproval(
        owner_user_id=owner, workflow_id=workflow.id, step_id=step.id,
        tool_key="activate_plan", tool_version="1",
        argument_digest="sha256:" + "a" * 64,
        rationale="test", risk_class="R2_DURABLE_PRIVATE", decision="PENDING",
        plan_version=workflow.plan_version,
        call_version="cv:" + "b" * 64,
    )
    scoped.add(approval)
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    back = (
        await scoped.execute(select(AgentApproval).where(AgentApproval.id == approval.id))
    ).scalar_one()
    assert back.plan_version == 2
    assert back.call_version == "cv:" + "b" * 64
    assert back.decision == "PENDING"


@pytest.mark.asyncio
async def test_agent_tool_call_roundtrip(scoped, owner):
    """The exact operation the corrupted mapper would have failed."""
    workflow = await _workflow(scoped, owner)
    call = AgentToolCall(
        owner_user_id=owner, workflow_id=workflow.id,
        tool_key="get_timeline", tool_version="1", risk_class="R0_READ_ONLY",
        argument_digest="sha256:" + "0" * 64,
        redacted_arguments={"limit": 5}, outcome="SUCCEEDED", duration_ms=12,
    )
    scoped.add(call)
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    back = (
        await scoped.execute(select(AgentToolCall).where(AgentToolCall.id == call.id))
    ).scalar_one()
    assert back.tool_key == "get_timeline"
    assert back.outcome == "SUCCEEDED"
    assert back.redacted_arguments == {"limit": 5}
    assert not hasattr(back, "call_version")


@pytest.mark.asyncio
async def test_outbox_roundtrip_with_lease_state(scoped, owner):
    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="QUEUED", role="operator",
    )
    scoped.add(step)
    await scoped.flush()

    # A CLAIMED row must carry both a holder and a lease. The earlier version of
    # this test inserted CLAIMED with lease_expires_at NULL and passed, which is
    # a row no lease-expiry query can ever reclaim.
    row = AgentDispatchOutbox(
        owner_user_id=owner, workflow_id=workflow.id, step_id=step.id,
        dispatch_key=f"{step.id}:1", state="CLAIMED", attempts=1,
        claimed_by="worker-a",
        lease_expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5),
        traceparent="00-" + "a" * 32 + "-" + "b" * 16 + "-01",
    )
    scoped.add(row)
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    back = (
        await scoped.execute(
            select(AgentDispatchOutbox).where(AgentDispatchOutbox.id == row.id)
        )
    ).scalar_one()
    assert back.state == "CLAIMED"
    assert back.claimed_by == "worker-a"
    assert back.attempts == 1
    assert back.lease_expires_at is not None
    assert back.next_attempt_at is not None


@pytest.mark.asyncio
async def test_cross_owner_rows_are_invisible_under_forced_rls(scoped, owner, app_engine):
    """Forced RLS must hide another owner's rows from the app role."""
    workflow = await _workflow(scoped, owner)
    await scoped.commit()

    stranger = uuid4()
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as other:
        await other.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(stranger)}
        )
        found = (
            await other.execute(select(AgentWorkflow).where(AgentWorkflow.id == workflow.id))
        ).scalar_one_or_none()
        assert found is None, "another owner could read this workflow"

        # And cannot mutate it.
        result = await other.execute(
            text("UPDATE agent_workflows SET title = 'hijacked' WHERE id = :w"),
            {"w": workflow.id},
        )
        assert result.rowcount == 0, "another owner could update this workflow"


@pytest.mark.asyncio
async def test_outbox_state_check_accepts_exactly_three_values(scoped, owner):
    """Behavioural proof of the CHECK, not a string search in its definition."""
    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="QUEUED", role="operator",
    )
    scoped.add(step)
    await scoped.flush()

    # Each legal state is inserted in a shape the row-integrity CHECK also
    # accepts, so this test isolates the state *set* rather than the shape.
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
    now = dt.datetime.now(dt.timezone.utc)
    shapes = [
        ("RETRYABLE", {}),
        ("CLAIMED", {"claimed_by": "worker-a", "lease_expires_at": future}),
        ("SENT", {"sent_at": now}),
    ]
    for index, (state, extra) in enumerate(shapes):
        columns = ["owner_user_id", "workflow_id", "step_id", "dispatch_key", "state", *extra]
        placeholders = [":o", ":w", ":s", ":k", ":st", *[f":{c}" for c in extra]]
        await scoped.execute(
            text(
                f"INSERT INTO agent_dispatch_outbox ({', '.join(columns)}) "
                f"VALUES ({', '.join(placeholders)})"
            ),
            {"o": owner, "w": workflow.id, "s": step.id, "k": f"ok-{index}", "st": state, **extra},
        )

    for bad in ("PENDING", "retryable", "SENT ", "", "DONE"):
        with pytest.raises(Exception) as caught:
            await scoped.execute(
                text(
                    "INSERT INTO agent_dispatch_outbox "
                    "(owner_user_id, workflow_id, step_id, dispatch_key, state) "
                    "VALUES (:o, :w, :s, :k, :st)"
                ),
                {"o": owner, "w": workflow.id, "s": step.id, "k": f"bad-{bad}", "st": bad},
            )
        assert "ck_agent_dispatch_state" in str(caught.value), bad
        await scoped.rollback()
        await scoped.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )


@pytest.mark.asyncio
async def test_pending_approval_requires_step_and_call_version(scoped, owner):
    workflow = await _workflow(scoped, owner)

    # PENDING with no step_id.
    with pytest.raises(Exception) as caught:
        await scoped.execute(
            text(
                "INSERT INTO agent_approvals (owner_user_id, workflow_id, tool_key, "
                "tool_version, argument_digest, rationale, risk_class, decision, call_version) "
                "VALUES (:o, :w, 't', '1', :d, 'r', 'R2_DURABLE_PRIVATE', 'PENDING', 'cv:x')"
            ),
            {"o": owner, "w": workflow.id, "d": "sha256:" + "a" * 64},
        )
    assert "ck_agent_approval_pending_bound" in str(caught.value)
    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    # plan_version below 1.
    with pytest.raises(Exception) as caught:
        await scoped.execute(
            text(
                "INSERT INTO agent_approvals (owner_user_id, workflow_id, tool_key, "
                "tool_version, argument_digest, rationale, risk_class, decision, plan_version) "
                "VALUES (:o, :w, 't', '1', :d, 'r', 'R2_DURABLE_PRIVATE', 'REJECTED', 0)"
            ),
            {"o": owner, "w": workflow.id, "d": "sha256:" + "a" * 64},
        )
    assert "ck_agent_approval_plan_version" in str(caught.value)


@pytest.mark.asyncio
async def test_approval_cannot_bind_to_a_step_from_another_workflow(scoped, owner):
    """Independent foreign keys are each satisfied by rows that have nothing to
    do with each other, so an approval could legally point at a step belonging
    to a different workflow. The trigger is what forbids it."""
    first = await _workflow(scoped, owner)
    second = await _workflow(scoped, owner)
    step_of_second = AgentStep(
        owner_user_id=owner, workflow_id=second.id, ordinal=1, key="s1",
        state="WAITING_APPROVAL", role="operator",
    )
    scoped.add(step_of_second)
    await scoped.flush()

    with pytest.raises(Exception) as caught:
        await scoped.execute(
            text(
                "INSERT INTO agent_approvals (owner_user_id, workflow_id, step_id, tool_key, "
                "tool_version, argument_digest, rationale, risk_class, decision, call_version) "
                "VALUES (:o, :w, :s, 't', '1', :d, 'r', 'R2_DURABLE_PRIVATE', 'PENDING', 'cv:x')"
            ),
            {
                "o": owner, "w": first.id, "s": step_of_second.id,
                "d": "sha256:" + "a" * 64,
            },
        )
    assert "different workflow" in str(caught.value)


@pytest.mark.asyncio
async def test_approval_cannot_bind_to_another_owners_step(scoped, owner, app_engine, client):
    """A wrong owner id must be refused even though both foreign keys resolve."""
    from app.tests.conftest import register_user

    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="WAITING_APPROVAL", role="operator",
    )
    scoped.add(step)
    await scoped.commit()

    stranger_response, _e, _p = await register_user(client, chosen_name="Bee")
    assert stranger_response.status_code == 201
    stranger = UUID(stranger_response.json()["id"])

    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as other:
        await other.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(stranger)}
        )
        with pytest.raises(Exception) as caught:
            await other.execute(
                text(
                    "INSERT INTO agent_approvals (owner_user_id, workflow_id, step_id, "
                    "tool_key, tool_version, argument_digest, rationale, risk_class, "
                    "decision, call_version) "
                    "VALUES (:o, :w, :s, 't', '1', :d, 'r', 'R2_DURABLE_PRIVATE', "
                    "'PENDING', 'cv:x')"
                ),
                {
                    "o": stranger, "w": workflow.id, "s": step.id,
                    "d": "sha256:" + "a" * 64,
                },
            )
        # Under forced RLS the stranger cannot see the step at all, so the
        # trigger reports it as not visible rather than as a mismatch. Either
        # message is a refusal; what matters is that the row is not written.
        assert "agent_approval_binding" in str(caught.value) or "violates" in str(caught.value)


@pytest.mark.asyncio
async def test_a_correctly_bound_approval_is_accepted(scoped, owner):
    """Guards the three tests above from passing because the trigger rejects
    everything."""
    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="WAITING_APPROVAL", role="operator",
    )
    scoped.add(step)
    await scoped.flush()

    await scoped.execute(
        text(
            "INSERT INTO agent_approvals (owner_user_id, workflow_id, step_id, tool_key, "
            "tool_version, argument_digest, rationale, risk_class, decision, call_version) "
            "VALUES (:o, :w, :s, 't', '1', :d, 'r', 'R2_DURABLE_PRIVATE', 'PENDING', 'cv:x')"
        ),
        {"o": owner, "w": workflow.id, "s": step.id, "d": "sha256:" + "a" * 64},
    )
    count = (
        await scoped.execute(
            text("SELECT count(*) FROM agent_approvals WHERE step_id = :s"), {"s": step.id}
        )
    ).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_outbox_state_shape_invariants(scoped, owner):
    """State and the columns that give it meaning are constrained together.
    A CLAIMED row with no lease is unreclaimable; a SENT row with no sent_at is
    a published message with no record of when."""
    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="QUEUED", role="operator",
    )
    scoped.add(step)
    await scoped.flush()

    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
    now = dt.datetime.now(dt.timezone.utc)

    async def insert(key, **cols):
        columns = ["owner_user_id", "workflow_id", "step_id", "dispatch_key", *cols]
        values = {"o": owner, "w": workflow.id, "s": step.id, "k": key, **cols}
        placeholders = [":o", ":w", ":s", ":k", *[f":{c}" for c in cols]]
        await scoped.execute(
            text(
                f"INSERT INTO agent_dispatch_outbox ({', '.join(columns)}) "
                f"VALUES ({', '.join(placeholders)})"
            ),
            values,
        )

    async def rejected(key, **cols):
        with pytest.raises(Exception) as caught:
            await insert(key, **cols)
        assert "ck_agent_dispatch_state_shape" in str(caught.value), (key, cols)
        await scoped.rollback()
        await scoped.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )

    # Invalid shapes.
    await rejected("bad-claimed-no-holder", state="CLAIMED", lease_expires_at=future)
    await rejected("bad-claimed-no-lease", state="CLAIMED", claimed_by="w")
    await rejected("bad-sent-no-sent-at", state="SENT")
    await rejected("bad-retryable-sent-at", state="RETRYABLE", sent_at=now)
    await rejected("bad-retryable-leased", state="RETRYABLE", claimed_by="w",
                   lease_expires_at=future)
    await rejected("bad-claimed-and-sent", state="CLAIMED", claimed_by="w",
                   lease_expires_at=future, sent_at=now)

    # Valid shapes commit and reload.
    workflow2 = await _workflow(scoped, owner)
    step2 = AgentStep(
        owner_user_id=owner, workflow_id=workflow2.id, ordinal=1, key="s2",
        state="QUEUED", role="operator",
    )
    scoped.add(step2)
    await scoped.flush()

    await scoped.execute(
        text(
            "INSERT INTO agent_dispatch_outbox "
            "(owner_user_id, workflow_id, step_id, dispatch_key, state) "
            "VALUES (:o, :w, :s, 'ok-retryable', 'RETRYABLE')"
        ),
        {"o": owner, "w": workflow2.id, "s": step2.id},
    )
    await scoped.execute(
        text(
            "INSERT INTO agent_dispatch_outbox "
            "(owner_user_id, workflow_id, step_id, dispatch_key, state, claimed_by, "
            " lease_expires_at) "
            "VALUES (:o, :w, :s, 'ok-claimed', 'CLAIMED', 'worker-a', :lease)"
        ),
        {"o": owner, "w": workflow2.id, "s": step2.id, "lease": future},
    )
    await scoped.execute(
        text(
            "INSERT INTO agent_dispatch_outbox "
            "(owner_user_id, workflow_id, step_id, dispatch_key, state, sent_at) "
            "VALUES (:o, :w, :s, 'ok-sent', 'SENT', :sent)"
        ),
        {"o": owner, "w": workflow2.id, "s": step2.id, "sent": now},
    )
    kept = (
        await scoped.execute(
            text("SELECT count(*) FROM agent_dispatch_outbox WHERE workflow_id = :w"),
            {"w": workflow2.id},
        )
    ).scalar()
    assert kept == 3


@pytest.mark.asyncio
async def test_every_claimed_row_can_be_found_by_lease_expiry(scoped, owner):
    """The point of the constraint: a reclaim query must be able to see every
    CLAIMED row."""
    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="QUEUED", role="operator",
    )
    scoped.add(step)
    await scoped.flush()
    await scoped.execute(
        text(
            "INSERT INTO agent_dispatch_outbox "
            "(owner_user_id, workflow_id, step_id, dispatch_key, state, claimed_by, "
            " lease_expires_at) "
            "VALUES (:o, :w, :s, 'expired', 'CLAIMED', 'dead-worker', now() - interval '1 min')"
        ),
        {"o": owner, "w": workflow.id, "s": step.id},
    )
    reclaimable = (
        await scoped.execute(
            text(
                "SELECT count(*) FROM agent_dispatch_outbox "
                "WHERE state = 'CLAIMED' AND lease_expires_at < now() AND workflow_id = :w"
            ),
            {"w": workflow.id},
        )
    ).scalar()
    assert reclaimable == 1

    unreclaimable = (
        await scoped.execute(
            text(
                "SELECT count(*) FROM agent_dispatch_outbox "
                "WHERE state = 'CLAIMED' AND lease_expires_at IS NULL"
            )
        )
    ).scalar()
    assert unreclaimable == 0, "a CLAIMED row with no lease is stranded forever"
