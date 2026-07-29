"""The first writes in the spine.

Three properties must hold for every draft tool, and each of them is a way model
output could otherwise become owner truth without anyone deciding.
"""

import inspect

import pytest

from app.agentic import handlers, registry
from app.agentic.enums import RiskClass
from app.agentic.tools import PRIVATE_DRAFT

DRAFT_HANDLERS = [
    handlers.create_draft_plan,
    handlers.create_memory_candidate,
    handlers.create_research_brief,
    handlers.create_insight_candidate,
    handlers.create_timeline_draft,
]


@pytest.fixture(autouse=True)
def bound():
    handlers.bind_read_only_handlers()
    handlers.bind_draft_handlers()


def test_read_and_write_binding_are_separable():
    """A caller must be able to enable reads without enabling any write."""
    source = inspect.getsource(handlers)
    assert "def bind_read_only_handlers" in source
    assert "def bind_draft_handlers" in source
    # No draft tool is bound inside the read-only function.
    read_fn = inspect.getsource(handlers.bind_read_only_handlers)
    assert "create_" not in read_fn


def test_no_draft_handler_writes_owner_written_provenance():
    """The owner did not write it; NUR proposed it. A draft that lied about its
    origin would poison the record permanently."""
    for fn in DRAFT_HANDLERS:
        source = inspect.getsource(fn)
        assert "OWNER_WRITTEN" not in source, fn.__name__
        assert "MODEL_PROVENANCE" in source or "provenance_label" in source, fn.__name__


def test_every_draft_declares_model_provenance_in_its_result():
    for fn in DRAFT_HANDLERS:
        assert "provenance_label" in inspect.getsource(fn), fn.__name__


def test_nothing_is_created_in_an_accepted_or_active_state():
    assert '"DRAFT"' in inspect.getsource(handlers.create_draft_plan)
    assert '"PENDING"' in inspect.getsource(handlers.create_memory_candidate)
    assert '"CANDIDATE"' in inspect.getsource(handlers.create_insight_candidate)
    assert '"DRAFT"' in inspect.getsource(handlers.create_research_brief)


def test_memory_candidate_never_sets_an_approved_memory_id():
    """There is no path from a tool to owner memory."""
    source = inspect.getsource(handlers.create_memory_candidate)
    assert "approved_memory_id" not in source or "stays null" in source
    assert "ACTIVE" not in source and "APPROVED" not in source


def test_no_tool_exists_to_promote_a_candidate():
    keys = set(registry.all_keys())
    for forbidden in ("approve_memory", "promote_memory", "write_memory", "accept_memory"):
        assert forbidden not in keys


def test_insight_doubt_is_required_not_defaulted():
    """A default would let a caller skip the hardest sentence in the product."""
    params = inspect.signature(handlers.create_insight_candidate).parameters
    doubt = params["what_nur_may_be_wrong_about"]
    assert doubt.default is inspect.Parameter.empty


@pytest.mark.asyncio
async def test_insight_rejects_an_empty_doubt():
    with pytest.raises(ValueError, match="where NUR may be wrong"):
        await handlers.create_insight_candidate(
            None, None, title="t", claim="c", what_nur_may_be_wrong_about="   "
        )


def test_timeline_draft_carries_no_schedule():
    """A draft that quietly carried a date would be a reminder nobody agreed to."""
    source = inspect.getsource(handlers.create_timeline_draft)
    # Check the model construction, not the docstring: the constructor must not
    # pass scheduled_for at all, and the result must say so explicitly.
    construction = source[source.index("TimelineEvent("):source.index("db.add(event)")]
    assert "scheduled_for" not in construction, "draft must not set a schedule"
    assert '"scheduled_for": None' in source


def test_all_draft_tools_are_r1_and_reversible():
    for spec in PRIVATE_DRAFT:
        assert spec.contract.risk_class is RiskClass.R1_PRIVATE_DRAFT
        assert spec.contract.reversible


def test_bound_draft_tools_match_their_declared_contracts():
    for key in ("create_draft_plan", "create_memory_candidate", "create_research_brief",
                "create_insight_candidate", "create_timeline_draft"):
        assert registry.is_bound(key)
        assert registry.contract(key).risk_class is RiskClass.R1_PRIVATE_DRAFT


def test_the_highest_consequence_tools_stay_unbound():
    """Three R2 tools are deliberately never bound, and it is not the whole class.

    This assertion used to cover every R2 tool with the reasoning that they
    "must not be callable from this phase". That premise is gone: the exact-call
    approval machinery exists precisely so a durable tool *can* run behind
    recorded consent, `bind_durable_handlers` binds three of them, and
    `test_durable_handlers.py` proves each refuses without an approval bound to
    its exact arguments.

    What remains true — and is the guarantee worth pinning — is that a Capsule
    crossing the owner's privacy boundary, a project run that spends budget, and
    task completion have no owner-reviewed flow yet. Declared and unbound is the
    honest state for those: they raise rather than half-working.
    """
    for key in ("create_capsule", "queue_project_run", "complete_task"):
        with pytest.raises(registry.UnboundToolError):
            registry.handler(key)


def test_bound_durable_tools_are_bound_and_gated_by_approval():
    """The complement of the above: the three that are bound are genuinely
    callable, and every one of them is R2 — so the policy engine forces an
    explicit owner decision before any of them executes."""
    from app.agentic.handlers import bind_all_handlers

    bind_all_handlers()
    for key in ("activate_plan", "schedule_timeline_event", "accept_or_correct_insight"):
        assert registry.is_bound(key), f"{key} should be callable behind approval"
        assert registry.contract(key).risk_class is RiskClass.R2_DURABLE_PRIVATE
