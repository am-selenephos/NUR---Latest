"""Workflow and step states for the NUR Agency Plane.

The transition tables here are the reason this module exists as data rather than
scattered `if` statements. Two properties have to hold and both are easy to lose
in hand-written checks:

  * DRAFT can never reach RUNNING. Every path to execution passes through
    planning, policy and — where the policy demands it — an owner approval. A
    single missing guard somewhere in a service is all it takes to give NUR
    silent agency, which is the one thing the product may not have.

  * Terminal states are terminal. A run that has already reported SUCCEEDED must
    not later move to FAILED because a duplicate queue delivery arrived late.

Keeping the graph declarative means the invariants are testable directly, rather
than inferred from whichever call sites happen to be exercised.
"""

from __future__ import annotations

from enum import StrEnum


class WorkflowState(StrEnum):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    POLICY_REVIEW = "POLICY_REVIEW"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    VERIFYING = "VERIFYING"
    NEEDS_REVISION = "NEEDS_REVISION"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class StepState(StrEnum):
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class RiskClass(StrEnum):
    """Risk is a property of the tool, not of the model's confidence."""

    R0_READ_ONLY = "R0_READ_ONLY"
    R1_PRIVATE_DRAFT = "R1_PRIVATE_DRAFT"
    R2_DURABLE_PRIVATE = "R2_DURABLE_PRIVATE"
    R3_EXTERNAL = "R3_EXTERNAL"
    R4_IRREVERSIBLE = "R4_IRREVERSIBLE"


class ApprovalDecision(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EDITED = "EDITED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class InitiativeLevel(StrEnum):
    OFF = "OFF"
    SUGGEST = "SUGGEST"
    PREPARE = "PREPARE"
    INTERNAL = "INTERNAL"
    CONNECTED = "CONNECTED"
    DELEGATED = "DELEGATED"


WORKFLOW_TERMINAL: frozenset[WorkflowState] = frozenset(
    {
        WorkflowState.SUCCEEDED,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
        WorkflowState.EXPIRED,
    }
)

STEP_TERMINAL: frozenset[StepState] = frozenset(
    {
        StepState.SUCCEEDED,
        StepState.FAILED,
        StepState.SKIPPED,
        StepState.CANCELLED,
    }
)

WORKFLOW_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.DRAFT: frozenset({WorkflowState.PLANNING, WorkflowState.CANCELLED}),
    WorkflowState.PLANNING: frozenset(
        {WorkflowState.PLAN_READY, WorkflowState.FAILED, WorkflowState.CANCEL_REQUESTED}
    ),
    WorkflowState.PLAN_READY: frozenset(
        {WorkflowState.POLICY_REVIEW, WorkflowState.CANCEL_REQUESTED}
    ),
    # Policy decides between "needs a human" and "cleared to run". There is no
    # third door out of POLICY_REVIEW into execution.
    WorkflowState.POLICY_REVIEW: frozenset(
        {
            WorkflowState.WAITING_APPROVAL,
            WorkflowState.APPROVED,
            WorkflowState.FAILED,
            WorkflowState.CANCEL_REQUESTED,
        }
    ),
    WorkflowState.WAITING_APPROVAL: frozenset(
        {
            WorkflowState.APPROVED,
            WorkflowState.CANCELLED,
            WorkflowState.EXPIRED,
            WorkflowState.CANCEL_REQUESTED,
        }
    ),
    WorkflowState.APPROVED: frozenset({WorkflowState.QUEUED, WorkflowState.CANCEL_REQUESTED}),
    WorkflowState.QUEUED: frozenset(
        {WorkflowState.RUNNING, WorkflowState.FAILED, WorkflowState.CANCEL_REQUESTED}
    ),
    WorkflowState.RUNNING: frozenset(
        {
            WorkflowState.PAUSED,
            WorkflowState.VERIFYING,
            WorkflowState.WAITING_APPROVAL,
            WorkflowState.FAILED,
            WorkflowState.CANCEL_REQUESTED,
        }
    ),
    # A paused run resumes into RUNNING; it never skips verification.
    WorkflowState.PAUSED: frozenset(
        {
            WorkflowState.RUNNING,
            WorkflowState.WAITING_APPROVAL,
            WorkflowState.CANCEL_REQUESTED,
            WorkflowState.EXPIRED,
        }
    ),
    WorkflowState.VERIFYING: frozenset(
        {
            WorkflowState.SUCCEEDED,
            WorkflowState.NEEDS_REVISION,
            WorkflowState.FAILED,
            WorkflowState.CANCEL_REQUESTED,
        }
    ),
    WorkflowState.NEEDS_REVISION: frozenset(
        {WorkflowState.PLANNING, WorkflowState.FAILED, WorkflowState.CANCEL_REQUESTED}
    ),
    WorkflowState.CANCEL_REQUESTED: frozenset({WorkflowState.CANCELLED, WorkflowState.FAILED}),
    WorkflowState.SUCCEEDED: frozenset(),
    WorkflowState.FAILED: frozenset(),
    WorkflowState.CANCELLED: frozenset(),
    WorkflowState.EXPIRED: frozenset(),
}

STEP_TRANSITIONS: dict[StepState, frozenset[StepState]] = {
    StepState.PENDING: frozenset(
        {StepState.BLOCKED, StepState.READY, StepState.SKIPPED, StepState.CANCELLED}
    ),
    StepState.BLOCKED: frozenset({StepState.READY, StepState.SKIPPED, StepState.CANCELLED}),
    StepState.READY: frozenset(
        {StepState.WAITING_APPROVAL, StepState.QUEUED, StepState.CANCELLED}
    ),
    StepState.WAITING_APPROVAL: frozenset(
        {StepState.QUEUED, StepState.SKIPPED, StepState.CANCELLED, StepState.FAILED}
    ),
    StepState.QUEUED: frozenset({StepState.RUNNING, StepState.FAILED, StepState.CANCELLED}),
    StepState.RUNNING: frozenset(
        {
            StepState.VERIFYING,
            StepState.WAITING_APPROVAL,
            StepState.FAILED,
            StepState.CANCELLED,
        }
    ),
    StepState.VERIFYING: frozenset(
        {StepState.SUCCEEDED, StepState.FAILED, StepState.CANCELLED}
    ),
    StepState.SUCCEEDED: frozenset(),
    StepState.FAILED: frozenset({StepState.QUEUED}),  # retry re-queues the same step
    StepState.SKIPPED: frozenset(),
    StepState.CANCELLED: frozenset(),
}


class TransitionError(RuntimeError):
    """Raised when a caller attempts a transition the state machine forbids."""


def assert_workflow_transition(current: WorkflowState, nxt: WorkflowState) -> None:
    if nxt not in WORKFLOW_TRANSITIONS[current]:
        raise TransitionError(f"workflow cannot move {current} -> {nxt}")


def assert_step_transition(current: StepState, nxt: StepState) -> None:
    if nxt not in STEP_TRANSITIONS[current]:
        raise TransitionError(f"step cannot move {current} -> {nxt}")


def reachable_workflow_states(start: WorkflowState) -> set[WorkflowState]:
    """Breadth-first closure. Used to prove DRAFT cannot reach RUNNING without
    passing through policy and approval."""
    seen: set[WorkflowState] = set()
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for nxt in WORKFLOW_TRANSITIONS[node]:
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen
