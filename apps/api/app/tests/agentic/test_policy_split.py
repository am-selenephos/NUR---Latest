"""Permitted vs auto-run are different questions.

Behavioural tests only — every one drives `evaluate` and asserts the decision.
The previous single field decided both, so widening what could be approved also
widened what could run unattended.
"""

import pytest

from app.agentic.enums import InitiativeLevel, RiskClass
from app.agentic.policy import Decision, OwnerPolicy, ToolContract, evaluate
from app.agentic.policy_store import capabilities_for
from app.agentic.registry import contract
from app.agentic.tools import KNOWN_CAPABILITIES

READ = "get_timeline"
DRAFT = "create_draft_plan"


def policy(**kw):
    base = dict(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        permitted_tools=frozenset({READ, DRAFT, "x"}),
        granted_capabilities=KNOWN_CAPABILITIES,
    )
    base.update(kw)
    return OwnerPolicy(**base)


def test_empty_permitted_set_grants_nothing_by_capability():
    assert capabilities_for(frozenset()) == frozenset()


def test_capabilities_derive_from_permitted_tools_only():
    granted = capabilities_for(frozenset({READ}))
    assert granted == frozenset({"read_timeline"})
    # A tool named only for auto-run contributes no capability of its own.
    assert "draft_plans" not in granted


def test_permitted_but_not_auto_run_asks_rather_than_denies():
    """Refusing here would make the owner's own permission useless."""
    verdict = evaluate(contract(READ), policy(permitted_tools=frozenset({READ})))
    assert verdict.decision is Decision.REQUIRE_APPROVAL
    assert "not enabled for unattended" in verdict.reason


def test_permitted_and_auto_run_within_limits_allows():
    verdict = evaluate(
        contract(READ),
        policy(permitted_tools=frozenset({READ}), auto_run_tools=frozenset({READ})),
    )
    assert verdict.decision is Decision.ALLOW


def test_unpermitted_tool_denies_and_cannot_reach_approval():
    """An inbox that can grant a capability the workflow never had would be an
    escalation mechanism wearing a consent interface."""
    verdict = evaluate(contract(DRAFT), policy(permitted_tools=frozenset({READ})))
    assert verdict.decision is Decision.DENY
    assert "not permitted" in verdict.reason


def test_auto_run_without_permission_cannot_execute():
    """auto_run must never act as a second permission grant."""
    verdict = evaluate(
        contract(DRAFT),
        policy(permitted_tools=frozenset({READ}), auto_run_tools=frozenset({DRAFT})),
    )
    assert verdict.decision is Decision.DENY


def test_denied_overrides_both():
    verdict = evaluate(
        contract(READ),
        policy(
            permitted_tools=frozenset({READ}),
            auto_run_tools=frozenset({READ}),
            denied_tools=frozenset({READ}),
        ),
    )
    assert verdict.decision is Decision.DENY
    assert "denied list" in verdict.reason


def test_an_empty_auto_run_set_means_ask_not_deny():
    for key in (READ, DRAFT):
        verdict = evaluate(
            contract(key),
            policy(permitted_tools=frozenset({READ, DRAFT}), auto_run_tools=frozenset()),
        )
        assert verdict.decision is Decision.REQUIRE_APPROVAL, key


def test_unknown_tool_grants_no_capability():
    assert capabilities_for(frozenset({"shell_exec"})) == frozenset()


def test_external_still_never_auto_runs_even_when_permitted_and_auto_run():
    external = ToolContract(
        key="x", version="1", risk_class=RiskClass.R3_EXTERNAL,
    )
    verdict = evaluate(
        external,
        policy(
            permitted_tools=frozenset({"x"}),
            auto_run_tools=frozenset({"x"}),
            max_risk_class=RiskClass.R4_IRREVERSIBLE,
        ),
    )
    assert verdict.decision is Decision.REQUIRE_APPROVAL


def test_missing_capability_still_denies_even_when_permitted_and_auto_run():
    verdict = evaluate(
        contract(READ),
        policy(
            permitted_tools=frozenset({READ}),
            auto_run_tools=frozenset({READ}),
            granted_capabilities=frozenset(),
        ),
    )
    assert verdict.decision is Decision.DENY
    assert verdict.denied_capabilities == frozenset({"read_timeline"})


def test_an_unconfigured_permitted_set_denies_on_permission_alone():
    """Not via the capability gate — permission must stand by itself."""
    verdict = evaluate(
        contract(READ), policy(permitted_tools=frozenset(), granted_capabilities=frozenset())
    )
    assert verdict.decision is Decision.DENY
    assert "not permitted" in verdict.reason


def test_owner_policy_no_longer_exposes_allowed_tools():
    """The legacy field must be gone from the runtime contract, not merely
    unused, or a caller can still set it and believe it does something."""
    assert not hasattr(OwnerPolicy(), "allowed_tools")
