"""The Agency Plane HTTP surface.

Route presence is asserted against the OpenAPI schema rather than `app.routes`,
because `app.routes` does not expose paths from included routers in a form that
survives a naive scan — checking it that way reports an empty surface for a
router that is in fact mounted.
"""

import pytest

from app.main import create_app


@pytest.fixture(scope="module")
def paths():
    return set(create_app().openapi()["paths"])


def test_every_declared_agentic_route_is_mounted(paths):
    for path in (
        "/api/v1/agentic/tools",
        "/api/v1/agentic/policy",
        "/api/v1/agentic/workflows",
        "/api/v1/agentic/workflows/{workflow_id}",
        "/api/v1/agentic/workflows/{workflow_id}/start",
        "/api/v1/agentic/workflows/{workflow_id}/cancel",
        "/api/v1/agentic/workflows/{workflow_id}/retry",
        "/api/v1/agentic/workflows/{workflow_id}/events",
        "/api/v1/agentic/approvals",
        "/api/v1/agentic/approvals/{approval_id}/decide",
    ):
        assert path in paths, f"{path} is not mounted"


def test_the_decide_route_requires_csrf():
    """A state-changing route without CSRF is a cross-site approval."""
    import inspect
    from app.api.v1 import agentic

    source = inspect.getsource(agentic.decide_approval)
    decorator = inspect.getsource(agentic).split("async def decide_approval")[0]
    assert "require_csrf" in decorator.rsplit("@router.post", 1)[-1] or "require_csrf" in source


def test_owner_lifecycle_writes_require_csrf_and_trusted_origin():
    """Every owner mutation crosses both browser-write boundaries."""
    import inspect
    from app.api.v1 import agentic

    source = inspect.getsource(agentic)
    for function_name in (
        "put_policy",
        "create_workflow",
        "start_workflow",
        "cancel_workflow",
        "retry_workflow",
        "decide_approval",
    ):
        before = source.split(f"async def {function_name}", 1)[0]
        decorator = before.rsplit("@router.", 1)[-1]
        assert "require_csrf" in decorator
        assert "require_trusted_origin" in decorator
        assert "require_agentic_mutation_rate" in decorator


def test_tool_catalog_exposes_bound_state():
    """Hiding unbound tools would make the surface look more capable than it is."""
    import inspect
    from app.api.v1 import agentic

    assert '"bound"' in inspect.getsource(agentic.list_tools)


def test_missing_workflow_returns_404_not_403():
    """Confirming a row exists but belongs to someone else is a disclosure."""
    import inspect
    from app.agentic import lifecycle_service

    source = inspect.getsource(lifecycle_service._owned_workflow)
    assert "status_code=404" in source
    # Check for a raised 403, not the literal string — the rationale comment
    # above the raise mentions 403, and matching that proves nothing.
    assert "status_code=403" not in source


def test_deciding_twice_conflicts_rather_than_overwriting():
    """Now enforced in the decision transaction rather than the route, and
    proven behaviourally in
    test_approval_http_e2e::test_a_second_decision_is_409_and_creates_no_extra_intent."""
    import inspect
    from app.agentic import decisions

    source = inspect.getsource(decisions._check_binding)
    assert "cannot be replaced" in source


def test_a_changed_request_cannot_be_decided_on_stale_arguments():
    """seen_digest, seen_plan_version and seen_call_version are all mandatory —
    an optional binding field is one a client can omit to skip the check."""
    from app.api.v1.agentic import ApprovalDecisionIn

    required = {
        name for name, field in ApprovalDecisionIn.model_fields.items() if field.is_required()
    }
    assert {"seen_digest", "seen_plan_version", "seen_call_version"} <= required


def test_workflow_detail_returns_the_context_manifest():
    """What a workflow was not allowed to see is how an owner checks its scope."""
    import inspect
    from app.agentic import lifecycle_service

    assert "context_manifest" in inspect.getsource(lifecycle_service._workflow_snapshot)
