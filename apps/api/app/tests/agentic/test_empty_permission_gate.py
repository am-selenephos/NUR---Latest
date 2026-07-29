"""An empty permitted set must deny, on its own.

The gate previously read `if policy.permitted_tools and key not in ...`, which
short-circuits when the set is empty. Every registered tool requires at least
one capability, so the capability check masked the hole for the whole catalog —
and the invariant was still false. A contract with no required capabilities is
the case that exposes it, so it is the case these tests use.
"""

import pytest

from app.agentic.enums import InitiativeLevel, RiskClass
from app.agentic.policy import Decision, OwnerPolicy, ToolContract, evaluate

# Deliberately capability-free: nothing downstream can rescue the permission gate.
FREE = ToolContract(
    key="zero_capability_tool",
    version="1",
    risk_class=RiskClass.R0_READ_ONLY,
    required_capabilities=frozenset(),
)


def maximal(**kw) -> OwnerPolicy:
    """Every other gate wide open, so only permission can produce a denial."""
    base = dict(
        initiative_level=InitiativeLevel.DELEGATED,
        max_risk_class=RiskClass.R4_IRREVERSIBLE,
        granted_capabilities=frozenset(),
        daily_budget_cents=1_000_000,
    )
    base.update(kw)
    return OwnerPolicy(**base)


def test_empty_permitted_set_denies_a_capability_free_tool():
    """The exact case the old short-circuit let through."""
    verdict = evaluate(FREE, maximal(auto_run_tools=frozenset({FREE.key})))
    assert verdict.decision is Decision.DENY
    assert "not permitted" in verdict.reason


def test_empty_permitted_set_denies_regardless_of_capability_requirements():
    for caps in (frozenset(), frozenset({"read_timeline"})):
        tool = ToolContract("t", "1", RiskClass.R0_READ_ONLY, required_capabilities=caps)
        verdict = evaluate(tool, maximal(granted_capabilities=caps))
        assert verdict.decision is Decision.DENY, caps
        assert "not permitted" in verdict.reason, caps


def test_permitted_zero_capability_without_auto_run_asks():
    verdict = evaluate(FREE, maximal(permitted_tools=frozenset({FREE.key})))
    assert verdict.decision is Decision.REQUIRE_APPROVAL


def test_permitted_zero_capability_with_auto_run_allows():
    verdict = evaluate(
        FREE,
        maximal(
            permitted_tools=frozenset({FREE.key}),
            auto_run_tools=frozenset({FREE.key}),
        ),
    )
    assert verdict.decision is Decision.ALLOW


def test_auto_run_without_permission_denies():
    verdict = evaluate(FREE, maximal(auto_run_tools=frozenset({FREE.key})))
    assert verdict.decision is Decision.DENY


def test_denied_overrides_permitted_and_auto_run():
    verdict = evaluate(
        FREE,
        maximal(
            permitted_tools=frozenset({FREE.key}),
            auto_run_tools=frozenset({FREE.key}),
            denied_tools=frozenset({FREE.key}),
        ),
    )
    assert verdict.decision is Decision.DENY
    assert "denied list" in verdict.reason


def test_permission_denial_precedes_the_capability_denial():
    """Permission must stand alone; it must not be enforced by a later gate."""
    tool = ToolContract(
        "t", "1", RiskClass.R0_READ_ONLY, required_capabilities=frozenset({"read_timeline"})
    )
    verdict = evaluate(tool, maximal(granted_capabilities=frozenset()))
    assert "not permitted" in verdict.reason
    assert "capabilities" not in verdict.reason


@pytest.mark.parametrize("key", ["", "unknown_tool", "shell_exec", "../../etc/passwd"])
def test_unknown_or_corrupted_keys_fail_closed(key):
    tool = ToolContract(key, "1", RiskClass.R0_READ_ONLY)
    verdict = evaluate(tool, maximal(permitted_tools=frozenset({"something_else"})))
    assert verdict.decision is Decision.DENY


def test_every_registered_tool_denies_under_an_empty_permission_set():
    from app.agentic.registry import catalog

    for spec in catalog():
        verdict = evaluate(spec.contract, maximal(granted_capabilities=frozenset()))
        assert verdict.decision is Decision.DENY, spec.contract.key
