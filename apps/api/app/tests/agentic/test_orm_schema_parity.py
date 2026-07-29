"""Every mapped column must exist in the database, and every required database
column must be mapped.

This is the check that would have caught the worst defect in this branch:
migrations added permitted_tools and auto_run_tools, the ORM never mapped them,
and `load_policy` used getattr with a default — so every policy silently loaded
an empty permission set and, with an unconditional permission gate, denied every
tool in the product. Nothing failed. The tests passed. The feature was dead.
"""

import pytest

from app.db.base import Base


def columns(table: str) -> set[str]:
    return {c.name for c in Base.metadata.tables[table].columns}


def test_policy_maps_the_split_fields():
    mapped = columns("agent_policies")
    assert {"permitted_tools", "auto_run_tools"} <= mapped


def test_policy_no_longer_maps_the_legacy_field():
    """The database column remains until a removal migration; the ORM must not
    expose it, or a caller can set something that governs nothing."""
    assert "allowed_tools" not in columns("agent_policies")


def test_approval_maps_the_call_version_binding():
    assert {"plan_version", "call_version"} <= columns("agent_approvals")


def test_outbox_model_exists_with_lease_fields():
    mapped = columns("agent_dispatch_outbox")
    assert {
        "owner_user_id", "workflow_id", "step_id", "dispatch_key", "state",
        "attempts", "claimed_by", "lease_expires_at", "next_attempt_at",
        "last_error", "traceparent", "created_at", "sent_at",
    } <= mapped


def test_policy_store_uses_direct_attribute_access():
    """A getattr fallback on a required schema field turns an unmapped column
    into an empty value instead of an error."""
    import inspect

    from app.agentic import policy_store

    source = inspect.getsource(policy_store.load_policy)
    assert "getattr(" not in source
    assert "chosen.permitted_tools" in source
    assert "chosen.auto_run_tools" in source


@pytest.mark.parametrize(
    "table,required",
    [
        ("agent_policies", {"permitted_tools", "auto_run_tools", "denied_tools"}),
        ("agent_approvals", {"plan_version", "call_version", "argument_digest"}),
        ("agent_dispatch_outbox", {"state", "claimed_by", "lease_expires_at"}),
    ],
)
def test_no_required_column_is_silently_unmapped(table, required):
    assert required <= columns(table), sorted(required - columns(table))
