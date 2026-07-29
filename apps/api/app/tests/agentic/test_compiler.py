"""Compilation is the last cheap place to refuse a bad plan.

Each test here corresponds to a way a plan can be broken such that run time
either stalls forever or grades its own homework.
"""

import pytest

from app.agentic.compiler import (
    ProposedStep,
    compile_plan,
    topological_order,
)
from app.agentic.enums import InitiativeLevel, RiskClass, StepState
from app.agentic.policy import OwnerPolicy
from app.agentic.tools import KNOWN_CAPABILITIES

# Compilation must not be blocked by unattended-use settings: a step that will
# ask for approval still compiles. auto_run is named broadly here so the
# compiler tests exercise compilation rather than the auto-run gate.
PERMISSIVE = OwnerPolicy(
    initiative_level=InitiativeLevel.INTERNAL,
    max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
    auto_run_tools=frozenset(
        {"get_plan", "get_timeline", "create_draft_plan", "activate_plan",
         "schedule_timeline_event", "create_insight_candidate"}
    ),
    granted_capabilities=KNOWN_CAPABILITIES,
    daily_budget_cents=1_000_000,
)


def step(key, tool="get_plan", role="operator", deps=()):
    return ProposedStep(key=key, role=role, tool_key=tool, depends_on=tuple(deps))


def errors_of(result):
    return {e.code for e in result.errors}


def test_empty_plan_is_refused():
    assert errors_of(compile_plan((), PERMISSIVE)) == {"EMPTY_PLAN"}


def test_cycle_is_rejected_at_compile_time():
    """A cycle at run time is a workflow that never finishes and never fails."""
    plan = (step("a", deps=("b",)), step("b", deps=("a",)))
    result = compile_plan(plan, PERMISSIVE)
    assert not result.ok
    assert "CYCLIC_PLAN" in errors_of(result)


def test_three_node_cycle_is_also_caught():
    plan = (step("a", deps=("c",)), step("b", deps=("a",)), step("c", deps=("b",)))
    assert "CYCLIC_PLAN" in errors_of(compile_plan(plan, PERMISSIVE))


def test_self_dependency_is_rejected():
    assert "SELF_DEPENDENCY" in errors_of(compile_plan((step("a", deps=("a",)),), PERMISSIVE))


def test_dangling_dependency_is_rejected():
    """`unlock_dependants` treats a missing dependency as unsatisfied, so this
    would stall permanently rather than crash."""
    assert "DANGLING_DEPENDENCY" in errors_of(compile_plan((step("a", deps=("ghost",)),), PERMISSIVE))


def test_duplicate_step_keys_are_rejected():
    assert "DUPLICATE_STEP_KEY" in errors_of(compile_plan((step("a"), step("a")), PERMISSIVE))


def test_unknown_tool_is_rejected():
    assert "UNKNOWN_TOOL" in errors_of(compile_plan((step("a", tool="shell_exec"),), PERMISSIVE))


def test_policy_denial_fails_compilation_and_carries_the_reason():
    """Compiling a step the gate refuses would strand the plan halfway, after
    the owner had already approved earlier steps."""
    restricted = OwnerPolicy(
        initiative_level=InitiativeLevel.SUGGEST,
        max_risk_class=RiskClass.R0_READ_ONLY,
        granted_capabilities=KNOWN_CAPABILITIES,
    )
    result = compile_plan((step("a", tool="schedule_timeline_event"),), restricted)
    assert not result.ok
    denial = next(e for e in result.errors if e.code == "POLICY_DENIED")
    assert "ceiling" in denial.message  # the policy's own words, not a generic string


def test_verifier_cannot_verify_its_own_step():
    plan = (
        ProposedStep("work", "verifier", "get_plan"),
        ProposedStep("check", "verifier", "get_plan", depends_on=("work",)),
    )
    assert "SELF_VERIFICATION" in errors_of(compile_plan(plan, PERMISSIVE))


def test_verifier_must_depend_on_the_work_it_verifies():
    plan = (ProposedStep("check", "verifier", "get_plan"),)
    assert "VERIFIER_WITHOUT_SUBJECT" in errors_of(compile_plan(plan, PERMISSIVE))


def test_verifier_may_not_use_a_mutating_tool():
    plan = (
        ProposedStep("work", "operator", "create_draft_plan"),
        ProposedStep("check", "verifier", "activate_plan", depends_on=("work",)),
    )
    assert "VERIFIER_MUTATES" in errors_of(compile_plan(plan, PERMISSIVE))


def test_independent_verification_compiles():
    plan = (
        ProposedStep("work", "operator", "create_draft_plan"),
        ProposedStep("check", "verifier", "get_plan", depends_on=("work",)),
    )
    result = compile_plan(plan, PERMISSIVE)
    assert result.ok, result.errors
    assert [s.key for s in result.steps] == ["work", "check"]


def test_dependent_steps_start_blocked_and_roots_start_ready():
    plan = (step("a"), step("b", deps=("a",)))
    result = compile_plan(plan, PERMISSIVE)
    states = {s.key: s.state for s in result.steps}
    assert states["a"] is StepState.READY
    assert states["b"] is StepState.BLOCKED


def test_ordinals_follow_topological_order():
    plan = (step("c", deps=("b",)), step("a"), step("b", deps=("a",)))
    result = compile_plan(plan, PERMISSIVE)
    assert [s.key for s in result.steps] == ["a", "b", "c"]
    assert [s.ordinal for s in result.steps] == [1, 2, 3]


def test_compilation_is_deterministic():
    """Same plan, same ordinals — otherwise plan versions cannot be compared."""
    plan = (step("b", deps=("a",)), step("a"), step("c", deps=("a",)))
    first = compile_plan(plan, PERMISSIVE)
    second = compile_plan(plan, PERMISSIVE)
    assert [s.key for s in first.steps] == [s.key for s in second.steps]


def test_approval_keys_are_surfaced_up_front():
    """So an approval card can show the whole ask, not one step at a time."""
    # `get_plan` is named for unattended use; `create_draft_plan` is permitted
    # but not, so only the draft step should ask.
    suggest = OwnerPolicy(
        initiative_level=InitiativeLevel.SUGGEST,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        auto_run_tools=frozenset({"get_plan"}),
        granted_capabilities=KNOWN_CAPABILITIES,
    )
    plan = (step("read", tool="get_plan"), step("draft", tool="create_draft_plan", deps=("read",)))
    result = compile_plan(plan, suggest)
    assert result.ok, result.errors
    assert result.approval_keys == ("draft",)


def test_out_of_scope_plan_is_refused_entirely():
    result = compile_plan((step("a"),), PERMISSIVE, within_scope=False)
    assert not result.ok
    assert "POLICY_DENIED" in errors_of(result)


def test_capabilities_are_carried_onto_the_compiled_step():
    result = compile_plan((step("a", tool="get_timeline"),), PERMISSIVE)
    assert result.steps[0].requested_capabilities == ("read_timeline",)


@pytest.mark.parametrize(
    "plan,expected",
    [
        ((), []),
        ((ProposedStep("a", "operator", "get_plan"),), ["a"]),
    ],
)
def test_topological_order_edge_cases(plan, expected):
    assert topological_order(plan) == expected
