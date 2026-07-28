"""The execution loop: what turns a compiled plan into work that happened.

Everything this calls already exists and is tested in isolation — the claim, the
policy gate, the tool registry, the approval check, the event ledger, the
dependant unlock. The runtime is what makes them one loop, and the ordering is
the whole design:

    claim → policy → approval → execute → record → verify → unlock

Two orderings are non-negotiable.

Policy and approval are evaluated *after* the claim and *before* the handler. A
gate checked before claiming would let two workers both pass it; a gate checked
after execution is not a gate. The claim is what gives one worker the exclusive
right to ask the question at all.

The result is recorded before verification, not after. A step that crashed
during verification must not look like a step that never ran — the work already
happened, and an audit trail that omits it because a later stage failed is a
trail that lies by omission.

Provider-backed agent execution is deliberately absent. This loop runs
deterministic first-party tools only. Adding a model call here without the
guardrails, budget accounting and checkpointing that a bounded agent run needs
would be the kind of shortcut that makes an agentic layer look finished while
being unsafe.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic import registry
from app.agentic.approvals import StoredApproval
from app.agentic.enums import ApprovalDecision, StepState
from app.agentic.observability import TraceContext
from app.agentic.orchestrator import argument_digest, claim_step, record_event, transition_step
from app.agentic.policy import Decision, OwnerPolicy, evaluate
from app.agentic.redaction import redact_arguments, telemetry_safe


@dataclass(frozen=True)
class StepOutcome:
    ok: bool
    state: StepState
    reason: str
    result: dict[str, Any] | None = None
    duration_ms: int = 0


class RuntimeRefusal(RuntimeError):
    """Raised when the loop declines to execute. Never swallowed silently."""


async def _load_step(db: AsyncSession, owner_user_id: uuid.UUID, step_id: uuid.UUID):
    row = await db.execute(
        text(
            """
            SELECT id, workflow_id, key, state, role, tool_key, tool_version,
                   risk_class, input_refs, approval_required, attempt
              FROM agent_steps
             WHERE id = :step AND owner_user_id = :owner
            """
        ),
        {"step": step_id, "owner": owner_user_id},
    )
    return row.mappings().first()


async def _record_tool_call(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    step_id: uuid.UUID,
    tool_key: str,
    tool_version: str,
    risk_class: str,
    arguments: dict,
    outcome: str,
    denial_reason: str | None,
    duration_ms: int,
    trace_id: str,
) -> None:
    """Every invocation is recorded, including the ones that were refused.

    A denial is the more interesting row: it is the evidence that the gate did
    its job. An audit trail holding only successful calls cannot demonstrate
    that anything was ever prevented.
    """
    await db.execute(
        text(
            """
            INSERT INTO agent_tool_calls (
                owner_user_id, workflow_id, step_id, tool_key, tool_version,
                risk_class, argument_digest, redacted_arguments, outcome,
                denial_reason, duration_ms, trace_id
            ) VALUES (
                :owner, :workflow, :step, :tool, :version, :risk, :digest,
                CAST(:args AS jsonb), :outcome, :denial, :duration, :trace
            )
            """
        ),
        {
            "owner": owner_user_id,
            "workflow": workflow_id,
            "step": step_id,
            "tool": tool_key,
            "version": tool_version,
            "risk": risk_class,
            "digest": argument_digest(tool_key, tool_version, arguments),
            "args": __import__("json").dumps(redact_arguments(arguments)),
            "outcome": outcome,
            "denial": denial_reason,
            "duration": duration_ms,
            "trace": trace_id,
        },
    )


async def execute_step(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    step_id: uuid.UUID,
    policy: OwnerPolicy,
    trace: TraceContext,
    worker: str,
    approval: StoredApproval | None = None,
    within_scope: bool = True,
) -> StepOutcome:
    """Run one step through the full loop.

    Returns a StepOutcome rather than raising for expected refusals — a policy
    denial and a lost claim are both normal states of the system, and turning
    them into exceptions would make ordinary operation look like failure in the
    logs. Genuine faults still raise.
    """
    claim = await claim_step(db, owner_user_id=owner_user_id, step_id=step_id, worker_id=worker)
    if not claim.claimed:
        # A duplicate delivery. Not an error; the other worker has it.
        return StepOutcome(False, StepState.QUEUED, claim.reason)

    step = await _load_step(db, owner_user_id, step_id)
    if step is None:
        raise RuntimeRefusal("claimed a step that cannot be re-read; RLS context is wrong")

    workflow_id = step["workflow_id"]
    tool_key = step["tool_key"]
    arguments = dict(step["input_refs"] or {})

    if not tool_key:
        await transition_step(
            db, owner_user_id=owner_user_id, step_id=step_id,
            current=StepState.RUNNING, nxt=StepState.FAILED,
        )
        return StepOutcome(False, StepState.FAILED, "step declares no tool")

    contract = registry.contract(tool_key)

    # ── Gate. After the claim so only one worker asks; before the handler so a
    #    refusal costs nothing. ──
    verdict = evaluate(contract, policy, within_scope=within_scope)
    if verdict.decision is Decision.DENY:
        await _record_tool_call(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
            tool_key=tool_key, tool_version=contract.version,
            risk_class=contract.risk_class.value, arguments=arguments,
            outcome="DENIED", denial_reason=verdict.reason[:120], duration_ms=0,
            trace_id=trace.trace_id,
        )
        await record_event(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
            event_type="STEP_DENIED", summary=verdict.reason,
            from_state=StepState.RUNNING.value, to_state=StepState.FAILED.value,
            trace_id=trace.trace_id,
        )
        await transition_step(
            db, owner_user_id=owner_user_id, step_id=step_id,
            current=StepState.RUNNING, nxt=StepState.FAILED,
        )
        return StepOutcome(False, StepState.FAILED, verdict.reason)

    if verdict.decision is Decision.REQUIRE_APPROVAL:
        held = (
            approval is not None
            and approval.decision in (ApprovalDecision.APPROVED, ApprovalDecision.EDITED)
        )
        if not held:
            # Pausing is a first-class outcome, not a failure. The step goes back
            # to WAITING_APPROVAL and the owner is asked.
            await record_event(
                db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
                event_type="STEP_AWAITING_APPROVAL", summary=verdict.reason,
                from_state=StepState.RUNNING.value, to_state=StepState.WAITING_APPROVAL.value,
                trace_id=trace.trace_id,
            )
            await transition_step(
                db, owner_user_id=owner_user_id, step_id=step_id,
                current=StepState.RUNNING, nxt=StepState.WAITING_APPROVAL,
            )
            return StepOutcome(False, StepState.WAITING_APPROVAL, verdict.reason)

    # ── Execute. The handler re-checks approval for durable tools; that
    #    duplication is intentional defence in depth. ──
    handler = registry.handler(tool_key)
    started = time.monotonic()
    try:
        kwargs = dict(arguments)
        if approval is not None:
            kwargs["approval"] = approval
        result = await handler(db, owner_user_id, **kwargs)
        duration_ms = int((time.monotonic() - started) * 1000)
    except Exception as error:  # noqa: BLE001 - recorded, then re-raised as a step failure
        duration_ms = int((time.monotonic() - started) * 1000)
        await _record_tool_call(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
            tool_key=tool_key, tool_version=contract.version,
            risk_class=contract.risk_class.value, arguments=arguments,
            outcome="FAILED", denial_reason=type(error).__name__, duration_ms=duration_ms,
            trace_id=trace.trace_id,
        )
        await record_event(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
            event_type="STEP_FAILED",
            # The exception type, never its message: a message can carry the
            # owner text the tool was handling.
            summary=f"{tool_key} raised {type(error).__name__}",
            from_state=StepState.RUNNING.value, to_state=StepState.FAILED.value,
            trace_id=trace.trace_id,
        )
        await transition_step(
            db, owner_user_id=owner_user_id, step_id=step_id,
            current=StepState.RUNNING, nxt=StepState.FAILED,
        )
        return StepOutcome(False, StepState.FAILED, type(error).__name__, duration_ms=duration_ms)

    # ── Record before verifying. Work that happened must appear in the ledger
    #    even if a later stage fails. ──
    await _record_tool_call(
        db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
        tool_key=tool_key, tool_version=contract.version,
        risk_class=contract.risk_class.value, arguments=arguments,
        outcome="SUCCEEDED", denial_reason=None, duration_ms=duration_ms,
        trace_id=trace.trace_id,
    )
    await record_event(
        db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
        event_type="STEP_EXECUTED", summary=f"{tool_key} completed",
        detail=telemetry_safe({"duration_ms": duration_ms}),
        from_state=StepState.RUNNING.value, to_state=StepState.VERIFYING.value,
        trace_id=trace.trace_id,
    )
    await transition_step(
        db, owner_user_id=owner_user_id, step_id=step_id,
        current=StepState.RUNNING, nxt=StepState.VERIFYING,
    )
    return StepOutcome(True, StepState.VERIFYING, "executed", result=result, duration_ms=duration_ms)
