"""The defects the founder identified, asserted so they cannot return.

Source-position checks here are supplementary architecture assertions, not
runtime proof — real database and worker-path tests are the next phase. What
these do prove is that the two structural faults are gone: a second claim site,
and a loop that stops at VERIFYING.
"""

import inspect

from app.agentic import runtime, verifier
from app.agentic.verifier import Verdict, verify_step_result
from app.workers import agentic_tasks


def test_there_is_exactly_one_claim_site():
    """Two claim sites is not a duplicated line; it is a loop that cannot run —
    the worker claimed, then the runtime found the step already RUNNING and
    refused."""
    worker_source = inspect.getsource(agentic_tasks)
    assert "claim_step(" not in worker_source, "the worker must not claim"
    assert worker_source.count("run_step(") >= 1, "the worker must call the runtime"

    runtime_source = inspect.getsource(runtime)
    assert runtime_source.count("await claim_step(") == 1


def test_the_worker_calls_the_runtime_entry_point():
    assert "from app.agentic.runtime import run_step" in inspect.getsource(agentic_tasks)


def test_the_loop_reaches_a_terminal_state_not_verifying():
    source = inspect.getsource(runtime.run_step)
    assert "StepState.SUCCEEDED" in source
    assert "StepState.FAILED" in source
    assert "current=StepState.VERIFYING" in source


def test_the_loop_unlocks_dependants_and_aggregates_the_workflow():
    source = inspect.getsource(runtime.run_step)
    assert "unlock_dependants(" in source
    assert "_aggregate_workflow(" in source


def test_dependants_are_queued_by_the_worker():
    """Queued in the worker, not the runtime, so the runtime stays testable
    without a broker."""
    source = inspect.getsource(agentic_tasks._execute_step)
    assert 'outcome.get("unlocked"' in source
    assert "execute_agentic_step_task.delay(" in source


def test_a_verifier_crash_preserves_execution_evidence():
    source = inspect.getsource(runtime.run_step)
    crash = source.index("verifier_error")
    assert "VERIFIER_ERROR" in source
    assert "execution evidence preserved" in source
    # The result is still persisted on the crash path.
    assert "_persist_step_result(" in source[crash:]


def test_results_are_persisted_not_left_in_a_return_value():
    source = inspect.getsource(runtime._persist_step_result)
    for column in ("result", "verification_verdict", "artifact_ids", "trace_id", "completed_at"):
        assert column in source
    assert "result_digest" in source


def test_workflow_state_is_computed_from_steps_not_tracked():
    """A separately maintained counter drifts the first time a step is reclaimed
    or re-planned."""
    source = inspect.getsource(runtime._aggregate_workflow)
    assert "FILTER (WHERE state = 'SUCCEEDED')" in source
    assert "FILTER (WHERE state = 'FAILED')" in source


# ── verifier behaviour ───────────────────────────────────────────────────────

def test_a_missing_result_fails_verification():
    assert verify_step_result("get_plan", None).verdict is Verdict.FAIL


def test_an_honest_no_op_is_revise_not_fail():
    """The call was fine; the step did not achieve its aim. That is a planning
    problem, not a defect."""
    result = verify_step_result("activate_plan", {"changed": False, "reason": "already active"})
    assert result.verdict is Verdict.REVISE


def test_a_write_that_does_not_report_change_fails():
    assert verify_step_result("create_draft_plan", {"plan_id": "x"}).verdict is Verdict.FAIL


def test_a_created_record_without_provenance_fails():
    result = verify_step_result("create_draft_plan", {"created": True, "plan_id": "x"})
    assert result.verdict is Verdict.FAIL
    assert any("provenance" in r for r in result.reasons)


def test_a_well_formed_draft_passes():
    result = verify_step_result(
        "create_draft_plan",
        {"created": True, "plan_id": "x", "provenance_label": "MODEL_GENERATED"},
    )
    assert result.verdict is Verdict.PASS


def test_a_scheduled_draft_timeline_event_fails_verification():
    result = verify_step_result(
        "create_timeline_draft",
        {"created": True, "event_id": "x", "provenance_label": "MODEL_GENERATED",
         "scheduled_for": "2026-08-04"},
    )
    assert result.verdict is Verdict.FAIL


def test_read_only_results_do_not_require_a_change_report():
    assert verify_step_result("get_timeline", {"count": 0, "events": []}).verdict is Verdict.PASS


def test_the_verifier_asks_no_model():
    source = inspect.getsource(verifier)
    for needle in ("openai", "Runner", "completions", "handler("):
        assert needle not in source


# ── capability fail-closed (P0) ──────────────────────────────────────────────

def test_capabilities_cannot_fall_back_to_the_full_set():
    """The previous expression was `(A & B) or C`, so an empty intersection
    granted every capability in the product. And `allowed_tools` holds tool
    keys, not capability names, so the intersection was empty almost always."""
    import ast
    from app.agentic import policy_store

    tree = ast.parse(inspect.getsource(policy_store))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) \
               and isinstance(node.body[0].value, ast.Constant):
                node.body = node.body[1:]
    assert "or KNOWN_CAPABILITIES" not in ast.unparse(tree)


def test_an_empty_allowlist_grants_nothing():
    from app.agentic.policy_store import capabilities_for

    assert capabilities_for(frozenset()) == frozenset()


def test_unknown_tool_keys_grant_nothing():
    from app.agentic.policy_store import capabilities_for

    assert capabilities_for(frozenset({"shell_exec", "not_a_tool"})) == frozenset()


def test_capabilities_are_the_union_of_allowed_tool_contracts():
    from app.agentic.policy_store import capabilities_for

    granted = capabilities_for(frozenset({"get_timeline", "get_plan"}))
    assert granted == frozenset({"read_timeline", "read_plans"})


def test_a_capability_bearing_tool_cannot_run_under_an_empty_policy():
    from app.agentic.policy import Decision, OwnerPolicy, evaluate
    from app.agentic.registry import contract
    from app.agentic.enums import InitiativeLevel, RiskClass

    empty = OwnerPolicy(
        initiative_level=InitiativeLevel.INTERNAL,
        max_risk_class=RiskClass.R2_DURABLE_PRIVATE,
        granted_capabilities=frozenset(),
    )
    assert evaluate(contract("get_timeline"), empty).decision is Decision.DENY


# ── post-claim gate state (P0) ───────────────────────────────────────────────

def test_policy_and_approval_load_after_the_claim():
    """State read before claiming may have changed by execution time — an owner
    revoking a policy or rejecting an approval in that window would be ignored."""
    source = inspect.getsource(runtime.run_step)
    claim = source.index("await claim_step(")
    policy = source.index("load_policy(")
    approval = source.index("load_step_approval(")
    execute = source.index("await execute_step(")
    assert claim < policy < execute
    assert claim < approval < execute


def test_the_worker_no_longer_preloads_gate_state():
    source = inspect.getsource(agentic_tasks)
    assert "load_policy(" not in source
    assert "load_step_approval(" not in source


def test_scope_for_policy_precedence_comes_from_the_claimed_workflow():
    source = inspect.getsource(runtime.run_step)
    assert "orbit_id" in source and "project_id" in source


# ── REVISE is not failure (P1) ───────────────────────────────────────────────

def test_revise_maps_to_needs_revision_not_failed():
    from app.agentic.enums import StepState

    source = inspect.getsource(runtime.run_step)
    assert "Verdict.REVISE" in source
    assert "StepState.NEEDS_REVISION" in source
    assert StepState.NEEDS_REVISION.value == "NEEDS_REVISION"


def test_needs_revision_is_not_terminal():
    """Re-planning must be able to re-queue the step."""
    from app.agentic.enums import STEP_TERMINAL, STEP_TRANSITIONS, StepState

    assert StepState.NEEDS_REVISION not in STEP_TERMINAL
    assert StepState.QUEUED in STEP_TRANSITIONS[StepState.NEEDS_REVISION]


def test_a_revising_step_keeps_dependants_blocked():
    """`unlock_dependants` promotes only when every dependency is SUCCEEDED."""
    from app.agentic.orchestrator import unlock_dependants

    assert "<> 'SUCCEEDED'" in inspect.getsource(unlock_dependants)


def test_workflow_reports_needs_revision():
    assert "NEEDS_REVISION" in inspect.getsource(runtime._aggregate_workflow)
