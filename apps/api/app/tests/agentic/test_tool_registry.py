"""Structural guarantees for the tool registry.

These do not test that a tool works — no handler is bound yet. They test the
properties that must hold before any handler exists, because once handlers land
a mistake here is a live capability rather than a failing assertion.
"""

import pytest

from app.agentic.enums import RiskClass
from app.agentic.policy import Decision, InitiativeLevel, OwnerPolicy, evaluate
from app.agentic import registry
from app.agentic.tools import (
    ALL_TOOLS,
    DURABLE,
    FORBIDDEN_CAPABILITIES,
    KNOWN_CAPABILITIES,
    PRIVATE_DRAFT,
    READ_ONLY,
)


def test_no_forbidden_capability_appears_in_any_contract():
    """The absences are the point. A first-party tool must never require shell,
    network, repo write, messaging, publish, deploy, spend, secrets — or
    write_memory, which would let model output become owner truth."""
    for spec in ALL_TOOLS:
        overlap = spec.contract.required_capabilities & FORBIDDEN_CAPABILITIES
        assert not overlap, f"{spec.contract.key} requires forbidden {sorted(overlap)}"


def test_no_tool_exists_for_a_forbidden_action():
    """Absence, not denial. A denied-but-present tool is one config edit from live."""
    banned_substrings = (
        "shell", "exec", "filesystem", "http_", "fetch_url", "repo_", "git_",
        "publish", "deploy", "pay", "charge", "send_email", "send_message",
        "secret", "credential", "delete_",
    )
    for spec in ALL_TOOLS:
        for banned in banned_substrings:
            assert banned not in spec.contract.key, f"{spec.contract.key} contains {banned!r}"


def test_no_tool_promotes_memory_to_owner_truth():
    keys = {s.contract.key for s in ALL_TOOLS}
    assert "create_memory_candidate" in keys
    for forbidden in ("write_memory", "approve_memory", "promote_memory", "save_memory"):
        assert forbidden not in keys


def test_every_capability_is_declared_known():
    """An undeclared capability name is either a typo or an escalation; both
    would silently widen what a workflow can be granted."""
    for spec in ALL_TOOLS:
        unknown = spec.contract.required_capabilities - KNOWN_CAPABILITIES
        assert not unknown, f"{spec.contract.key} requires unknown {sorted(unknown)}"


def test_read_only_tools_declare_no_writes():
    for spec in READ_ONLY:
        assert spec.contract.risk_class is RiskClass.R0_READ_ONLY
        assert spec.writes == (), f"{spec.contract.key} is R0 but declares writes"
        assert spec.idempotent, f"{spec.contract.key} is R0 and must be idempotent"


def test_read_only_tools_require_only_read_capabilities():
    for spec in READ_ONLY:
        for cap in spec.contract.required_capabilities:
            assert cap.startswith("read_"), f"{spec.contract.key} requires non-read {cap}"


def test_draft_tools_are_reversible_and_write_only_drafts():
    for spec in PRIVATE_DRAFT:
        assert spec.contract.risk_class is RiskClass.R1_PRIVATE_DRAFT
        assert spec.contract.reversible, f"{spec.contract.key} is a draft but not reversible"
        assert spec.writes, f"{spec.contract.key} is R1 but declares no write"


def test_durable_tools_are_r2_and_declare_what_they_change():
    for spec in DURABLE:
        assert spec.contract.risk_class is RiskClass.R2_DURABLE_PRIVATE
        assert spec.writes, f"{spec.contract.key} mutates but declares no write"


def test_capsule_creation_is_marked_irreversible():
    """A Capsule leaves the private boundary; the approval card must not call it
    reversible."""
    capsule = registry.spec("create_capsule")
    assert capsule.contract.reversible is False


def test_no_duplicate_keys():
    keys = [s.contract.key for s in ALL_TOOLS]
    assert len(keys) == len(set(keys))


def test_unknown_tool_raises_rather_than_returning_a_default():
    with pytest.raises(registry.UnknownToolError):
        registry.spec("get_everything")
    with pytest.raises(registry.UnknownToolError):
        registry.contract("shell_exec")


def test_declared_but_unbound_tool_cannot_be_executed():
    """A contract without a handler must fail loudly, not return an empty result
    a planner would treat as success."""
    with pytest.raises(registry.UnboundToolError):
        registry.handler("get_today_state")


def test_binding_an_undeclared_tool_is_rejected():
    """Otherwise a callable tool would exist that the policy engine never saw."""
    async def rogue(**_):  # pragma: no cover - never invoked
        return None

    with pytest.raises(registry.UnknownToolError):
        registry.bind("shell_exec", rogue)
    assert "shell_exec" not in registry.bound_keys()


def test_catalog_covers_every_declared_tool():
    assert len(registry.catalog()) == len(ALL_TOOLS)
    assert set(registry.all_keys()) == {s.contract.key for s in ALL_TOOLS}


def test_every_contract_is_evaluable_by_the_policy_engine():
    """The registry and the policy engine must agree on the contract shape, or
    a tool could exist that the gate cannot classify."""
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        granted_capabilities=KNOWN_CAPABILITIES,
    )
    for spec in ALL_TOOLS:
        verdict = evaluate(spec.contract, policy)
        assert verdict.decision in (Decision.ALLOW, Decision.REQUIRE_APPROVAL, Decision.DENY)


def test_read_only_tools_auto_run_at_suggest_but_drafts_do_not():
    """Confirms the registry's risk classes produce the intended default posture
    at NUR's default initiative level."""
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.SUGGEST,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        granted_capabilities=KNOWN_CAPABILITIES,
    )
    assert evaluate(registry.contract("get_plan"), policy).decision is Decision.ALLOW
    assert evaluate(registry.contract("create_draft_plan"), policy).decision is Decision.REQUIRE_APPROVAL
    assert evaluate(registry.contract("create_capsule"), policy).decision is Decision.REQUIRE_APPROVAL
