"""The state machine's job is to make silent agency structurally impossible.

These assert the two properties that cannot be checked by reading call sites:
no path from DRAFT to execution skips policy and approval, and terminal states
stay terminal under duplicate delivery.
"""

import pytest

from app.agentic.enums import (
    STEP_TERMINAL,
    STEP_TRANSITIONS,
    WORKFLOW_TERMINAL,
    WORKFLOW_TRANSITIONS,
    StepState,
    TransitionError,
    WorkflowState,
    assert_step_transition,
    assert_workflow_transition,
    reachable_workflow_states,
)


def test_draft_cannot_reach_running_directly():
    assert WorkflowState.RUNNING not in WORKFLOW_TRANSITIONS[WorkflowState.DRAFT]
    with pytest.raises(TransitionError):
        assert_workflow_transition(WorkflowState.DRAFT, WorkflowState.RUNNING)


def test_every_path_from_draft_to_running_passes_policy_review():
    """Remove POLICY_REVIEW and RUNNING must become unreachable from DRAFT.

    This is the real guarantee. Asserting only that DRAFT->RUNNING is absent
    would still pass if someone added DRAFT->APPROVED as a shortcut.
    """
    pruned = {
        state: frozenset(t for t in targets if t is not WorkflowState.POLICY_REVIEW)
        for state, targets in WORKFLOW_TRANSITIONS.items()
    }
    seen: set[WorkflowState] = set()
    frontier = [WorkflowState.DRAFT]
    while frontier:
        node = frontier.pop()
        for nxt in pruned[node]:
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    assert WorkflowState.RUNNING not in seen, (
        "RUNNING is reachable from DRAFT without passing through POLICY_REVIEW"
    )


def test_running_is_reachable_when_policy_review_is_present():
    """Guards the test above from passing because the graph is simply broken."""
    assert WorkflowState.RUNNING in reachable_workflow_states(WorkflowState.DRAFT)


def test_workflow_terminal_states_are_absorbing():
    for state in WORKFLOW_TERMINAL:
        assert WORKFLOW_TRANSITIONS[state] == frozenset(), state
        with pytest.raises(TransitionError):
            assert_workflow_transition(state, WorkflowState.RUNNING)


def test_succeeded_cannot_be_reopened_by_a_late_duplicate():
    for late in (WorkflowState.FAILED, WorkflowState.RUNNING, WorkflowState.QUEUED):
        with pytest.raises(TransitionError):
            assert_workflow_transition(WorkflowState.SUCCEEDED, late)


def test_step_terminal_states_are_absorbing_except_retry():
    for state in STEP_TERMINAL:
        if state is StepState.FAILED:
            # A failed step may be retried; that is the one intended re-entry.
            assert STEP_TRANSITIONS[state] == frozenset({StepState.QUEUED})
            continue
        assert STEP_TRANSITIONS[state] == frozenset(), state


def test_step_cannot_run_without_being_queued():
    with pytest.raises(TransitionError):
        assert_step_transition(StepState.READY, StepState.RUNNING)
    with pytest.raises(TransitionError):
        assert_step_transition(StepState.PENDING, StepState.RUNNING)


def test_step_cannot_succeed_without_verification():
    with pytest.raises(TransitionError):
        assert_step_transition(StepState.RUNNING, StepState.SUCCEEDED)
    assert_step_transition(StepState.RUNNING, StepState.VERIFYING)
    assert_step_transition(StepState.VERIFYING, StepState.SUCCEEDED)


def test_transition_tables_are_total():
    """Every declared state has an entry, so an unhandled state is a KeyError at
    import time rather than an unchecked transition at runtime."""
    assert set(WORKFLOW_TRANSITIONS) == set(WorkflowState)
    assert set(STEP_TRANSITIONS) == set(StepState)
