"""Exhaustive tests for the gate every tool call passes through.

The important ones are the products: every risk class against every initiative
level, asserted as a whole rather than sampled. A spot-check would pass against
a table with one wrong cell, and one wrong cell here is NUR taking an external
action nobody approved.
"""

import datetime as dt
import itertools

import pytest

from app.agentic.enums import InitiativeLevel, RiskClass
from app.agentic.policy import (
    AUTO_RUN_CEILING,
    INITIATIVE_ORDER,
    RISK_ORDER,
    Decision,
    OwnerPolicy,
    ToolContract,
    evaluate,
)

PERMISSIVE = OwnerPolicy(
    initiative_level=InitiativeLevel.DELEGATED,
    max_risk_class=RiskClass.R4_IRREVERSIBLE,
    daily_budget_cents=1_000_000,
)


def tool(risk: RiskClass, **kw) -> ToolContract:
    return ToolContract(key=kw.pop("key", "t"), version="1", risk_class=risk, **kw)


def test_external_never_auto_runs_at_any_initiative_level():
    """The load-bearing assertion of this module."""
    for level in INITIATIVE_ORDER:
        policy = OwnerPolicy(
            initiative_level=level,
            max_risk_class=RiskClass.R4_IRREVERSIBLE,
            daily_budget_cents=1_000_000,
        )
        verdict = evaluate(tool(RiskClass.R3_EXTERNAL), policy)
        assert verdict.decision is not Decision.ALLOW, (
            f"R3 auto-ran at initiative {level} — external action without approval"
        )


def test_no_initiative_level_has_an_auto_run_ceiling_above_r2():
    """Guards the table itself, not just its current outputs. If someone raises
    a ceiling to R3 later, this fails before any behaviour test would."""
    for level, ceiling in AUTO_RUN_CEILING.items():
        if ceiling is None:
            continue
        assert RISK_ORDER.index(ceiling) <= RISK_ORDER.index(RiskClass.R2_DURABLE_PRIVATE), (
            f"{level} may auto-run {ceiling}"
        )


def test_irreversible_is_denied_while_disabled():
    verdict = evaluate(tool(RiskClass.R4_IRREVERSIBLE), PERMISSIVE)
    assert verdict.decision is Decision.DENY
    assert "not enabled" in verdict.reason


def test_full_risk_by_initiative_matrix():
    """Every cell asserted, so no combination is left to assumption."""
    for level, risk in itertools.product(INITIATIVE_ORDER, RISK_ORDER):
        policy = OwnerPolicy(
            initiative_level=level,
            max_risk_class=RiskClass.R4_IRREVERSIBLE,
            daily_budget_cents=1_000_000,
        )
        decision = evaluate(tool(risk), policy).decision
        if level is InitiativeLevel.OFF:
            assert decision is Decision.DENY, (level, risk)
        elif risk is RiskClass.R4_IRREVERSIBLE:
            assert decision is Decision.DENY, (level, risk)
        elif risk is RiskClass.R3_EXTERNAL:
            assert decision is Decision.REQUIRE_APPROVAL, (level, risk)
        else:
            ceiling = AUTO_RUN_CEILING[level]
            expected = (
                Decision.ALLOW
                if ceiling is not None and RISK_ORDER.index(risk) <= RISK_ORDER.index(ceiling)
                else Decision.REQUIRE_APPROVAL
            )
            assert decision is expected, (level, risk, decision)


def test_denied_list_beats_an_allowlist_entry():
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        allowed_tools=frozenset({"t"}),
        denied_tools=frozenset({"t"}),
    )
    assert evaluate(tool(RiskClass.R0_READ_ONLY), policy).decision is Decision.DENY


def test_allowlist_narrows_rather_than_widens():
    """A non-empty allowlist must not grant anything; it only restricts."""
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        allowed_tools=frozenset({"other"}),
    )
    assert evaluate(tool(RiskClass.R0_READ_ONLY), policy).decision is Decision.REQUIRE_APPROVAL
    # And it cannot lift an external call into auto-run.
    permissive_list = OwnerPolicy(
        initiative_level=InitiativeLevel.CONNECTED,
        max_risk_class=RiskClass.R4_IRREVERSIBLE,
        allowed_tools=frozenset({"t"}),
    )
    assert evaluate(tool(RiskClass.R3_EXTERNAL), permissive_list).decision is Decision.REQUIRE_APPROVAL


def test_missing_capability_denies_rather_than_prompting():
    """Prompting would make the approval inbox an escalation vector."""
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        granted_capabilities=frozenset({"read_plan"}),
    )
    verdict = evaluate(
        tool(RiskClass.R0_READ_ONLY, required_capabilities=frozenset({"write_timeline"})), policy
    )
    assert verdict.decision is Decision.DENY
    assert verdict.denied_capabilities == frozenset({"write_timeline"})


def test_out_of_scope_is_denied_even_for_read_only():
    assert (
        evaluate(tool(RiskClass.R0_READ_ONLY), PERMISSIVE, within_scope=False).decision
        is Decision.DENY
    )


def test_owner_risk_ceiling_is_enforced():
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL, max_risk_class=RiskClass.R1_PRIVATE_DRAFT
    )
    assert evaluate(tool(RiskClass.R2_DURABLE_PRIVATE), policy).decision is Decision.DENY


def test_budget_denies_only_after_permission_passes():
    """An owner must never be told 'not enough budget' for something they were
    never permitted to do — the remedy would be misleading."""
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R1_PRIVATE_DRAFT,
        daily_budget_cents=10,
        spent_today_cents=9,
    )
    over = evaluate(tool(RiskClass.R2_DURABLE_PRIVATE, estimated_cost_cents=100), policy)
    assert over.decision is Decision.DENY
    assert "ceiling" in over.reason  # permission, not budget

    within_permission = evaluate(tool(RiskClass.R1_PRIVATE_DRAFT, estimated_cost_cents=100), policy)
    assert within_permission.decision is Decision.DENY
    assert "budget" in within_permission.reason


def test_zero_budget_means_unlimited_not_blocked():
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        daily_budget_cents=0,
    )
    assert evaluate(tool(RiskClass.R0_READ_ONLY, estimated_cost_cents=999), policy).decision is Decision.ALLOW


@pytest.mark.parametrize(
    "window,hour,inside",
    [((22, 7), 23, True), ((22, 7), 3, True), ((22, 7), 12, False),
     ((9, 17), 12, True), ((9, 17), 20, False), ((9, 9), 9, False)],
)
def test_quiet_hours_wrap_around_midnight(window, hour, inside):
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        quiet_hours=window,
    )
    now = dt.datetime(2026, 7, 28, hour, tzinfo=dt.timezone.utc)
    decision = evaluate(tool(RiskClass.R0_READ_ONLY), policy, now=now).decision
    assert decision is (Decision.REQUIRE_APPROVAL if inside else Decision.ALLOW)


def test_quiet_hours_never_loosen_a_decision():
    """Quiet hours may only make the answer more conservative."""
    policy = OwnerPolicy(
        initiative_level=InitiativeLevel.CONNECTED,
        max_risk_class=RiskClass.R4_IRREVERSIBLE,
        quiet_hours=(0, 23),
    )
    now = dt.datetime(2026, 7, 28, 5, tzinfo=dt.timezone.utc)
    assert evaluate(tool(RiskClass.R3_EXTERNAL), policy, now=now).decision is Decision.REQUIRE_APPROVAL
    assert evaluate(tool(RiskClass.R4_IRREVERSIBLE), policy, now=now).decision is Decision.DENY


def test_initiative_off_denies_even_read_only():
    policy = OwnerPolicy(initiative_level=InitiativeLevel.OFF, max_risk_class=RiskClass.R4_IRREVERSIBLE)
    assert evaluate(tool(RiskClass.R0_READ_ONLY), policy).decision is Decision.DENY


def test_denials_carry_a_remedy_except_where_none_exists():
    policy = OwnerPolicy(initiative_level=InitiativeLevel.OFF)
    assert evaluate(tool(RiskClass.R0_READ_ONLY), policy).remedy
    # R4 has no remedy short of a code change, and must not pretend otherwise.
    assert evaluate(tool(RiskClass.R4_IRREVERSIBLE), PERMISSIVE).remedy is None
