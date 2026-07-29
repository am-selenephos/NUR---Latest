"""Daily spend and quiet hours, loaded from durable state rather than defaults.

`load_policy` read the budget ceiling but never the spend, and never the quiet
window — and `cost_cents` was never written to `agent_tool_calls` at all, so the
sum was always zero. The ceiling therefore could not bind no matter what an owner
set it to, and quiet hours were a column nothing consulted.

Spend is read from the tool-call ledger, so it survives a restart and is shared
across workers. A counter held in a worker process resets on deploy and is wrong
the moment a second worker exists.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers
from app.agentic.observability import new_trace
from app.agentic.policy import Decision, evaluate
from app.agentic.policy_store import daily_spend_cents, load_policy
from app.agentic.registry import contract
from app.agentic.runtime import run_step
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user

TOOL = "get_timeline"
# The only R0 tool in the catalog with a non-zero estimated cost would make this
# simpler; there isn't one, so spend rows are written directly where the point is
# the *arithmetic* rather than the handler.
COSTLY = "create_draft_plan"


@pytest.fixture(autouse=True)
def bound_handlers():
    handlers.bind_all_handlers()


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


async def _workflow(db, owner) -> uuid.UUID:
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
    )
    db.add(workflow)
    await db.flush()
    return workflow.id


async def _charge(db, owner, workflow_id, cents: int, *, days_ago: int = 0) -> None:
    """One durable tool-call row, as the runtime writes after a handler runs."""
    await db.execute(
        text(
            """
            INSERT INTO agent_tool_calls (
                owner_user_id, workflow_id, tool_key, tool_version, risk_class,
                argument_digest, outcome, cost_cents, created_at
            ) VALUES (
                :o, :w, 't', '1', 'R1_PRIVATE_DRAFT', :d, 'SUCCEEDED', :c,
                now() - make_interval(days => :days)
            )
            """
        ),
        {
            "o": owner, "w": workflow_id, "c": cents, "days": days_ago,
            "d": f"sha256:{uuid.uuid4().hex}",
        },
    )


async def _policy(db, owner, **columns) -> None:
    db.add(
        AgentPolicy(
            owner_user_id=owner,
            initiative_level=columns.pop("initiative_level", "INTERNAL"),
            max_risk_class=columns.pop("max_risk_class", "R2_DURABLE_PRIVATE"),
            permitted_tools=columns.pop("permitted_tools", [TOOL, COSTLY]),
            auto_run_tools=columns.pop("auto_run_tools", [TOOL, COSTLY]),
            **columns,
        )
    )
    await db.flush()


# ── daily spend ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spend_is_read_from_the_durable_ledger(scoped, owner):
    workflow_id = await _workflow(scoped, owner)
    await _policy(scoped, owner, daily_budget_cents=500)
    await _charge(scoped, owner, workflow_id, 120)
    await _charge(scoped, owner, workflow_id, 80)
    await scoped.commit()

    assert await daily_spend_cents(scoped, owner_user_id=owner) == 200

    policy = await load_policy(scoped, owner_user_id=owner)
    assert policy.spent_today_cents == 200, "load_policy ignored the ledger"
    assert policy.daily_budget_cents == 500


@pytest.mark.asyncio
async def test_under_budget_is_allowed_and_over_budget_is_denied(scoped, owner):
    workflow_id = await _workflow(scoped, owner)
    await _policy(scoped, owner, daily_budget_cents=100)
    await scoped.commit()

    tool = contract(TOOL)
    under = await load_policy(scoped, owner_user_id=owner)
    assert evaluate(tool, under).decision is not Decision.DENY

    # Spend right up to the ceiling.
    await _charge(scoped, owner, workflow_id, 100)
    await scoped.commit()

    over = await load_policy(scoped, owner_user_id=owner)
    assert over.spent_today_cents == 100
    costly = contract(COSTLY)
    verdict = evaluate(costly, over)
    if costly.estimated_cost_cents > 0:
        assert verdict.decision is Decision.DENY, verdict.reason
        assert "budget" in verdict.reason.lower()
    else:
        # A zero-cost tool projects to exactly the ceiling, which is not over it.
        assert verdict.decision is not Decision.DENY


@pytest.mark.asyncio
async def test_the_current_call_is_included_in_the_projection(scoped, owner):
    """The check is `spent + this call > budget`, not `spent > budget`. Charging
    only afterwards would let every single call exceed the ceiling by its own
    cost."""
    from app.agentic.policy import OwnerPolicy, ToolContract
    from app.agentic.enums import InitiativeLevel, RiskClass

    tool = ToolContract(
        key="x", version="1", risk_class=RiskClass.R0_READ_ONLY, estimated_cost_cents=30
    )
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        permitted_tools=frozenset({"x"}),
        auto_run_tools=frozenset({"x"}),
        granted_capabilities=frozenset(),
        daily_budget_cents=100,
        spent_today_cents=80,
    )
    verdict = evaluate(tool, policy)
    assert verdict.decision is Decision.DENY, "80 + 30 > 100 was allowed"
    assert "110" in verdict.reason


@pytest.mark.asyncio
async def test_yesterdays_spend_does_not_count_against_today(scoped, owner):
    workflow_id = await _workflow(scoped, owner)
    await _policy(scoped, owner, daily_budget_cents=100)
    await _charge(scoped, owner, workflow_id, 500, days_ago=1)
    await _charge(scoped, owner, workflow_id, 10)
    await scoped.commit()

    assert await daily_spend_cents(scoped, owner_user_id=owner) == 10, (
        "yesterday's spend leaked into today; the budget would never reset"
    )


@pytest.mark.asyncio
async def test_another_owners_spend_does_not_consume_this_budget(
    scoped, owner, client, app_engine
):
    workflow_id = await _workflow(scoped, owner)
    await _policy(scoped, owner, daily_budget_cents=100)
    await _charge(scoped, owner, workflow_id, 10)
    await scoped.commit()

    other, _e, _p = await register_user(client, chosen_name="Bee")
    stranger = uuid.UUID(other.json()["id"])
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(stranger)}
        )
        stranger_workflow = await _workflow(db, stranger)
        await _charge(db, stranger, stranger_workflow, 900)
        await db.commit()

    # Re-assert this session's RLS context: the fixture sets it session-scoped,
    # and the stranger's session above may have been handed the same pooled
    # connection and left its own owner id on it. Production sets the context
    # transaction-locally per request, so this is a harness concern only.
    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    assert await daily_spend_cents(scoped, owner_user_id=owner) == 10, (
        "another owner's spend was charged to this owner"
    )


@pytest.mark.asyncio
async def test_a_retry_does_not_double_charge(scoped, owner):
    """A duplicate delivery loses the claim and never reaches the handler, so it
    writes no tool-call row and adds no cost."""
    await _policy(scoped, owner, daily_budget_cents=10_000)
    workflow_id = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow_id, ordinal=1, key="a",
        state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
    )
    scoped.add(step)
    await scoped.flush()
    await scoped.commit()

    first = await run_step(
        scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w1"
    )
    await scoped.commit()
    assert first["executed"] is True
    after_one = await daily_spend_cents(scoped, owner_user_id=owner)

    second = await run_step(
        scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w2"
    )
    await scoped.commit()
    assert second["executed"] is False
    assert await daily_spend_cents(scoped, owner_user_id=owner) == after_one, (
        "a redelivery was charged a second time"
    )


@pytest.mark.asyncio
async def test_a_denied_call_is_not_charged(scoped, owner):
    """A policy that correctly refused work must not consume the budget it was
    protecting."""
    await _policy(
        scoped, owner, permitted_tools=[], auto_run_tools=[], daily_budget_cents=1_000
    )
    workflow_id = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow_id, ordinal=1, key="a",
        state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
    )
    scoped.add(step)
    await scoped.flush()
    await scoped.commit()

    outcome = await run_step(
        scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w1"
    )
    await scoped.commit()
    assert outcome["step_state"] == "FAILED", outcome

    denied = (
        await scoped.execute(
            text(
                "SELECT cost_cents FROM agent_tool_calls "
                "WHERE step_id = :s AND outcome = 'DENIED'"
            ),
            {"s": step.id},
        )
    ).scalar_one()
    assert denied == 0
    assert await daily_spend_cents(scoped, owner_user_id=owner) == 0


@pytest.mark.asyncio
async def test_zero_budget_means_unlimited_not_blocked(scoped, owner):
    """Explicit behaviour for the default. `daily_budget_cents = 0` is "no budget
    configured", which must not silently mean "nothing may ever run" — an owner
    who never opened the setting would find the product inert."""
    await _policy(scoped, owner, daily_budget_cents=0)
    workflow_id = await _workflow(scoped, owner)
    await _charge(scoped, owner, workflow_id, 5_000)
    await scoped.commit()

    policy = await load_policy(scoped, owner_user_id=owner)
    assert policy.daily_budget_cents == 0
    assert policy.spent_today_cents == 5_000
    assert evaluate(contract(TOOL), policy).decision is not Decision.DENY


# ── quiet hours ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quiet_hours_are_loaded_with_their_timezone(scoped, owner):
    await _policy(
        scoped, owner, quiet_hours={"start": 22, "end": 7, "tz": "Asia/Karachi"}
    )
    await scoped.commit()

    policy = await load_policy(scoped, owner_user_id=owner)
    assert policy.quiet_hours == (22, 7)
    assert policy.timezone_name == "Asia/Karachi"


@pytest.mark.asyncio
async def test_quiet_hours_are_evaluated_in_the_owners_zone(scoped, owner):
    """The defect a UTC-only reading would have: 19:00 UTC is 00:00 in Karachi,
    which is inside a 22:00-07:00 night, and 03:00 UTC is 08:00 there, which is
    outside it. Reading `.hour` off the UTC instant gets both backwards."""
    await _policy(
        scoped, owner, quiet_hours={"start": 22, "end": 7, "tz": "Asia/Karachi"}
    )
    await scoped.commit()
    policy = await load_policy(scoped, owner_user_id=owner)
    tool = contract(TOOL)

    midnight_local = dt.datetime(2026, 7, 29, 19, 0, tzinfo=dt.timezone.utc)
    verdict = evaluate(tool, policy, now=midnight_local)
    assert verdict.decision is Decision.REQUIRE_APPROVAL, (
        "00:00 in the owner's zone was treated as outside their night"
    )
    assert "quiet hours" in verdict.reason.lower()

    morning_local = dt.datetime(2026, 7, 29, 3, 0, tzinfo=dt.timezone.utc)
    assert evaluate(tool, policy, now=morning_local).decision is Decision.ALLOW, (
        "08:00 in the owner's zone was treated as inside their night"
    )


@pytest.mark.asyncio
async def test_an_overnight_window_is_one_night_not_two_halves(scoped, owner):
    await _policy(scoped, owner, quiet_hours={"start": 22, "end": 7, "tz": "UTC"})
    await scoped.commit()
    policy = await load_policy(scoped, owner_user_id=owner)
    tool = contract(TOOL)

    for hour, inside in ((21, False), (22, True), (23, True), (0, True), (6, True), (7, False)):
        now = dt.datetime(2026, 7, 29, hour, 0, tzinfo=dt.timezone.utc)
        verdict = evaluate(tool, policy, now=now)
        held = verdict.decision is Decision.REQUIRE_APPROVAL
        assert held is inside, f"hour {hour}: held={held}, expected inside={inside}"


@pytest.mark.asyncio
async def test_a_malformed_quiet_window_is_no_window(scoped, owner):
    """A typo must not invent a rule. Hours outside 0-23 are dropped rather than
    clamped into a valid-looking window the owner never wrote."""
    await _policy(scoped, owner, quiet_hours={"start": 99, "end": 7, "tz": "UTC"})
    await scoped.commit()
    policy = await load_policy(scoped, owner_user_id=owner)
    assert policy.quiet_hours is None
    assert policy.timezone_name == "UTC"


@pytest.mark.asyncio
async def test_an_unknown_timezone_degrades_to_utc_without_breaking_anything(scoped, owner):
    """An unrecognised zone must not disable quiet hours and must not crash.

    Both were real: failing open would run unattended work during exactly the
    window the owner asked to be left alone, and the zone is interpolated into
    `AT TIME ZONE` when spend is summed — PostgreSQL raises on an unknown name,
    so a typo in this jsonb made `load_policy` throw and every step execution for
    that owner fail. The zone is validated once at load and falls back to UTC.
    """
    await _policy(
        scoped, owner, quiet_hours={"start": 0, "end": 23, "tz": "Not/AZone"}
    )
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    policy = await load_policy(scoped, owner_user_id=owner)
    assert policy.quiet_hours == (0, 23), "an unknown zone disabled the window"
    assert policy.timezone_name == "UTC", "an unknown zone was passed through"

    now = dt.datetime(2026, 7, 29, 12, 0, tzinfo=dt.timezone.utc)
    assert evaluate(contract(TOOL), policy, now=now).decision is Decision.REQUIRE_APPROVAL

    # And the spend query, which is what actually raised.
    assert await daily_spend_cents(
        scoped, owner_user_id=owner, timezone_name=policy.timezone_name
    ) == 0


@pytest.mark.asyncio
async def test_scope_precedence_still_holds_for_runtime_state(scoped, owner):
    """A project policy overrides the account default, including its window."""
    from app.models.orbit import Orbit
    from app.models.projects import AMProject

    orbit = Orbit(owner_user_id=owner, title="O")
    scoped.add(orbit)
    await scoped.flush()
    project = AMProject(
        owner_user_id=owner, orbit_id=orbit.id, title="P", objective="o",
    )
    scoped.add(project)
    await scoped.flush()

    await _policy(scoped, owner, quiet_hours={"start": 1, "end": 2, "tz": "UTC"})
    scoped.add(
        AgentPolicy(
            owner_user_id=owner, project_id=project.id,
            initiative_level="INTERNAL", max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=[TOOL], auto_run_tools=[TOOL],
            quiet_hours={"start": 22, "end": 7, "tz": "Asia/Karachi"},
        )
    )
    await scoped.flush()
    await scoped.commit()

    account = await load_policy(scoped, owner_user_id=owner)
    assert account.quiet_hours == (1, 2)
    assert account.timezone_name == "UTC"

    scoped_to_project = await load_policy(
        scoped, owner_user_id=owner, project_id=project.id
    )
    assert scoped_to_project.quiet_hours == (22, 7)
    assert scoped_to_project.timezone_name == "Asia/Karachi"
