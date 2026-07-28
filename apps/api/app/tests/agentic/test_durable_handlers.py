"""Durable tools change what is true for the owner.

The property under test is that none of them can execute without proof that this
exact call was approved — enforced inside the handler, not merely upstream.
"""

import datetime as dt
import inspect

import pytest

from app.agentic import handlers, registry
from app.agentic.approvals import StoredApproval
from app.agentic.enums import ApprovalDecision, RiskClass
from app.agentic.orchestrator import argument_digest


@pytest.fixture(autouse=True)
def bound():
    handlers.bind_durable_handlers()


def proof(tool_key, arguments, version="1", decision=ApprovalDecision.APPROVED):
    return StoredApproval(
        tool_key=tool_key,
        tool_version=version,
        argument_digest=argument_digest(tool_key, version, arguments),
        redacted_arguments=arguments,
        decision=decision,
    )


@pytest.mark.asyncio
async def test_no_approval_refuses_before_touching_the_database():
    """`db` is None here on purpose: if the guard ran after the query this would
    raise AttributeError instead of ApprovalMissing."""
    with pytest.raises(handlers.ApprovalMissing, match="cannot run without an owner approval"):
        await handlers.activate_plan(None, None, plan_id="p1", approval=None)


@pytest.mark.asyncio
async def test_an_approval_for_different_arguments_is_refused():
    """The core replay defence: a yes for one payload is not a yes for another."""
    granted = proof("activate_plan", {"plan_id": "plan-a"})
    with pytest.raises(handlers.ApprovalMissing, match="ARGUMENTS_CHANGED"):
        await handlers.activate_plan(None, None, plan_id="plan-b", approval=granted)


@pytest.mark.asyncio
async def test_an_approval_for_a_different_tool_is_refused():
    granted = proof("schedule_timeline_event", {"plan_id": "plan-a"})
    with pytest.raises(handlers.ApprovalMissing, match="TOOL_CHANGED"):
        await handlers.activate_plan(None, None, plan_id="plan-a", approval=granted)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decision",
    [ApprovalDecision.PENDING, ApprovalDecision.REJECTED, ApprovalDecision.INVALIDATED],
)
async def test_a_non_approval_is_refused(decision):
    granted = proof("activate_plan", {"plan_id": "p"}, decision=decision)
    with pytest.raises(handlers.ApprovalMissing, match="NOT_APPROVED"):
        await handlers.activate_plan(None, None, plan_id="p", approval=granted)


@pytest.mark.asyncio
async def test_an_expired_approval_is_refused():
    granted = StoredApproval(
        tool_key="activate_plan", tool_version="1",
        argument_digest=argument_digest("activate_plan", "1", {"plan_id": "p"}),
        redacted_arguments={"plan_id": "p"},
        decision=ApprovalDecision.APPROVED,
        expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1),
    )
    with pytest.raises(handlers.ApprovalMissing, match="EXPIRED"):
        await handlers.activate_plan(None, None, plan_id="p", approval=granted)


def test_every_durable_handler_guards_before_it_queries():
    """A guard placed after the read would leak existence of another's row via
    timing or error shape."""
    for fn in (handlers.activate_plan, handlers.schedule_timeline_event,
               handlers.accept_or_correct_insight):
        source = inspect.getsource(fn)
        guard = source.index("_require_approval")
        query = source.index("await db.execute")
        assert guard < query, f"{fn.__name__} queries before checking approval"


def test_capsule_and_project_run_stay_unbound():
    """A Capsule crosses the private boundary and a project run spends budget.
    Declaring them while leaving them unbound is the honest state."""
    for key in ("create_capsule", "queue_project_run", "complete_task"):
        with pytest.raises(registry.UnboundToolError):
            registry.handler(key)


def test_bound_durable_tools_are_r2():
    for key in ("activate_plan", "schedule_timeline_event", "accept_or_correct_insight"):
        assert registry.is_bound(key)
        assert registry.contract(key).risk_class is RiskClass.R2_DURABLE_PRIVATE


def test_binding_layers_are_separable():
    """A deployment must be able to run reads and drafts with mutations off."""
    source = inspect.getsource(handlers)
    for fn in ("bind_read_only_handlers", "bind_draft_handlers", "bind_durable_handlers"):
        assert f"def {fn}" in source
    assert "activate_plan" not in inspect.getsource(handlers.bind_draft_handlers)


def test_correction_preserves_the_original_claim():
    """An Insight NUR got wrong, and the owner's correction, are both evidence.
    Overwriting the claim would make NUR's mistakes unauditable."""
    source = inspect.getsource(handlers.accept_or_correct_insight)
    assert "insight.correction = correction" in source
    assert "insight.claim =" not in source


def test_a_correction_must_say_what_is_true():
    source = inspect.getsource(handlers.accept_or_correct_insight)
    assert "a correction must say what is actually true" in source


def test_activating_a_non_draft_reports_no_change_rather_than_success():
    """A silent no-op reporting success is how duplicate delivery looks like it
    worked."""
    source = inspect.getsource(handlers.activate_plan)
    assert '"changed": False' in source
    assert 'only a DRAFT plan can be activated' in source
