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
