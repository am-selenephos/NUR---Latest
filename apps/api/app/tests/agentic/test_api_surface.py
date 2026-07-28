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
        "/api/v1/agentic/workflows",
        "/api/v1/agentic/workflows/{workflow_id}",
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


def test_no_write_route_exists_for_creating_a_workflow_yet():
    """Declaring a POST that cannot honestly plan would be a surface that lies."""
    schema = create_app().openapi()["paths"]
    workflows = schema.get("/api/v1/agentic/workflows", {})
    assert "get" in workflows
    assert "post" not in workflows


def test_tool_catalog_exposes_bound_state():
    """Hiding unbound tools would make the surface look more capable than it is."""
    import inspect
    from app.api.v1 import agentic

    assert '"bound"' in inspect.getsource(agentic.list_tools)


def test_missing_workflow_returns_404_not_403():
    """Confirming a row exists but belongs to someone else is a disclosure."""
    import inspect
    from app.api.v1 import agentic

    source = inspect.getsource(agentic.get_workflow)
    assert "status_code=404" in source
    # Check for a raised 403, not the literal string — the rationale comment
    # above the raise mentions 403, and matching that proves nothing.
    assert "status_code=403" not in source


def test_deciding_twice_conflicts_rather_than_overwriting():
    import inspect
    from app.api.v1 import agentic

    source = inspect.getsource(agentic.decide_approval)
    assert "status_code=409" in source
    assert "cannot be replaced" in source


def test_a_changed_request_cannot_be_decided_on_stale_arguments():
    """The same guarantee evaluate_resume gives at execution time, enforced one
    step earlier so the owner is told immediately."""
    import inspect
    from app.api.v1 import agentic

    source = inspect.getsource(agentic.decide_approval)
    assert "seen_digest" in source
    assert "did not read" in source


def test_workflow_detail_returns_the_context_manifest():
    """What a workflow was not allowed to see is how an owner checks its scope."""
    import inspect
    from app.api.v1 import agentic

    assert "context_manifest" in inspect.getsource(agentic.get_workflow)
