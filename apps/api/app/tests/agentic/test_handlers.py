"""Read-only handler binding.

The properties worth testing before any handler runs against data: bound tools
resolve, unbound ones still fail loudly, and nothing bound here is capable of a
write.
"""

import inspect

import pytest

from app.agentic import handlers, registry
from app.agentic.enums import RiskClass
from app.agentic.tools import READ_ONLY


@pytest.fixture(autouse=True)
def bound():
    handlers.bind_read_only_handlers()


def test_binding_returns_the_callable_keys():
    keys = set(handlers.bind_read_only_handlers())
    assert {
        "get_map_neighbourhood", "get_timeline", "search_approved_memory",
        "get_today_state", "get_plan", "get_system_snapshot", "get_orbit",
        "get_project", "get_project_evidence", "get_insight",
    } <= keys


def test_bound_tools_resolve_to_a_handler():
    for key in ("get_map_neighbourhood", "get_timeline", "search_approved_memory",
                "get_today_state", "get_plan", "get_insight"):
        assert callable(registry.handler(key))
        assert registry.is_bound(key)


def test_only_read_only_tools_are_bound():
    """A write tool bound in the read-only module would be an escalation that no
    other test would catch."""
    read_only_keys = {spec.contract.key for spec in READ_ONLY}
    for key in registry.bound_keys():
        assert key in read_only_keys, f"{key} is bound but is not read-only"
        assert registry.contract(key).risk_class is RiskClass.R0_READ_ONLY


def test_unbound_tools_still_fail_loudly():
    """An unimplemented tool must not return an empty result a planner would
    treat as a completed step."""
    # Still genuinely unbound: the one read-only tool without a handler, and
    # every draft tool. Both must fail rather than return an empty result.
    with pytest.raises(registry.UnboundToolError):
        registry.handler("get_omega_workspace_frame")
    with pytest.raises(registry.UnboundToolError):
        registry.handler("create_draft_plan")


def test_no_bound_handler_accepts_a_write_shaped_argument():
    forbidden = {"payload", "body", "content", "value", "data", "update", "delete"}
    for key in registry.bound_keys():
        params = set(inspect.signature(registry.handler(key)).parameters)
        leaked = forbidden & params
        assert not leaked, f"{key} accepts {sorted(leaked)}"


def test_every_bound_handler_takes_a_scoped_session_and_owner():
    """Handlers receive an already RLS-scoped session; none may open its own."""
    for key in registry.bound_keys():
        params = list(inspect.signature(registry.handler(key)).parameters)
        assert params[0] == "db", key
        assert params[1] == "owner_user_id", key


def test_timeline_limit_is_clamped_not_trusted():
    source = inspect.getsource(handlers.get_timeline)
    assert "min(" in source, "an unbounded limit would pull an entire history into context"


def test_memory_search_excludes_candidates():
    """The filter is the whole point: a candidate re-entering a run would carry
    the authority of owner truth without ever having been approved."""
    source = inspect.getsource(handlers.search_approved_memory)
    assert "APPROVED" in source
    doc = handlers.search_approved_memory.__doc__ or ""
    assert "candidate" in doc.lower()


def test_map_handler_reuses_the_endpoint_assembly():
    """Sharing one function makes drift impossible rather than merely unlikely."""
    assert "_map_snapshot" in inspect.getsource(handlers.get_map_neighbourhood)


def test_unknown_node_reports_not_found_rather_than_empty():
    """Saying 'nothing is connected to this' when the node does not exist is a
    false answer, not a null one."""
    source = inspect.getsource(handlers.get_map_neighbourhood)
    assert '"found": False' in source


def test_insight_handler_returns_doubt_with_the_claim():
    """An Insight quoted without its own account of where it might be wrong is
    the unlabelled certainty this product exists to refuse."""
    source = inspect.getsource(handlers.get_insight)
    assert "what_nur_may_be_wrong_about" in source
    assert "counter_evidence" in source
    assert "confidence_meaning" in source


def test_project_evidence_never_hides_verification_status():
    """Filtering unverified evidence away would let a later step cite it as
    though it had been checked."""
    source = inspect.getsource(handlers.get_project_evidence)
    assert "verification_status" in source


def test_orbit_handler_returns_privacy_scope():
    """Omitting it would let a later step treat a shared Orbit as private."""
    assert "privacy_scope" in inspect.getsource(handlers.get_orbit)


def test_system_definition_comes_from_the_catalog_not_the_database():
    """The founder-locked definition is not owner data and must not drift per
    owner."""
    assert "SYSTEMS" in inspect.getsource(handlers.get_system_snapshot)


def test_every_read_only_tool_except_omega_is_bound():
    from app.agentic.tools import READ_ONLY

    declared = {s.contract.key for s in READ_ONLY}
    bound = set(registry.bound_keys())
    assert declared - bound == {"get_omega_workspace_frame"}
