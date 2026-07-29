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


async def _persist_step_result(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    step_id: uuid.UUID,
    result: dict[str, Any] | None,
    verdict: str,
    duration_ms: int,
    trace_id: str,
) -> str:
    """Persist the output manifest, digest and verdict onto the step row.

    A handler's return value living only in a Python frame is not durability. A
    worker restart between execution and verification would otherwise lose all
    evidence of what the tool produced, leaving a row that says RUNNING and no
    way to tell whether the work happened.

    The manifest is redacted and bounded: identifiers, digests and counts, not
    the owner content itself, which already lives in the rows the tool wrote.
    """
    import json

    payload = redact_arguments(result or {})
    digest = argument_digest("__result__", "1", payload)
    manifest = {
        "keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "artifact_ids": [v for k, v in (payload.items() if isinstance(payload, dict) else [])
                         if k.endswith("_id") and isinstance(v, str)],
        "result_digest": digest,
        "duration_ms": duration_ms,
        "trace_id": trace_id,
    }
    await db.execute(
        text(
            """
            UPDATE agent_steps
               SET result = CAST(:result AS jsonb),
                   verification_verdict = :verdict,
                   artifact_ids = CAST(:artifacts AS jsonb),
                   trace_id = :trace,
                   completed_at = now(),
                   updated_at = now()
             WHERE id = :step AND owner_user_id = :owner
            """
        ),
        {
            "result": json.dumps({"manifest": manifest, "output": payload}),
            "verdict": verdict,
            "artifacts": json.dumps(manifest["artifact_ids"]),
            "trace": trace_id,
            "step": step_id,
            "owner": owner_user_id,
        },
    )
    return digest


async def _aggregate_workflow(
    db: AsyncSession, *, owner_user_id: uuid.UUID, workflow_id: uuid.UUID
) -> str:
    """Derive the workflow's state from its steps.

    Computed rather than tracked. A separately maintained counter drifts the
    first time a step is reclaimed or re-planned, and a workflow whose state
    disagrees with its own steps is worse than one with no state at all.
    """
    row = (
        await db.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE state = 'SUCCEEDED') AS ok,
                  count(*) FILTER (WHERE state = 'FAILED')    AS failed,
                  count(*) FILTER (WHERE state = 'WAITING_APPROVAL') AS waiting,
                  count(*) AS total
                FROM agent_steps
                WHERE workflow_id = :workflow AND owner_user_id = :owner
                """
            ),
            {"workflow": workflow_id, "owner": owner_user_id},
        )
    ).mappings().one()

    if row["total"] and row["ok"] == row["total"]:
        state = "SUCCEEDED"
    elif row["failed"]:
        state = "FAILED"
    elif row["waiting"]:
        state = "WAITING_APPROVAL"
    else:
        state = "RUNNING"

    await db.execute(
        text(
            "UPDATE agent_workflows SET state = :state, updated_at = now() "
            "WHERE id = :workflow AND owner_user_id = :owner"
        ),
        {"state": state, "workflow": workflow_id, "owner": owner_user_id},
    )
    return state


async def run_step(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    step_id: uuid.UUID,
    policy: OwnerPolicy,
    trace: TraceContext,
    worker: str,
    approval: StoredApproval | None = None,
    within_scope: bool = True,
) -> dict[str, Any]:
    """The single top-level entry point. The runtime owns the claim.

    There is exactly one claim site in the system and it is inside
    `execute_step`. The worker sets the RLS context and calls this; it does not
    claim. Two claim sites meant a worker that claimed and a runtime that then
    refused because the step was no longer QUEUED — the defect this replaces.

    After execution the loop actually closes: verify, persist, transition to a
    terminal state, unlock dependants, and recompute the workflow's state.
    """
    from app.agentic.orchestrator import unlock_dependants
    from app.agentic.verifier import Verdict, verify_step_result

    outcome = await execute_step(
        db,
        owner_user_id=owner_user_id,
        step_id=step_id,
        policy=policy,
        trace=trace,
        worker=worker,
        approval=approval,
        within_scope=within_scope,
    )

    step = await _load_step(db, owner_user_id, step_id)
    workflow_id = step["workflow_id"] if step else None

    # Not executed: denial, pause or a lost claim. Each already recorded its own
    # event and terminal-or-waiting state inside execute_step.
    if not outcome.ok:
        workflow_state = (
            await _aggregate_workflow(db, owner_user_id=owner_user_id, workflow_id=workflow_id)
            if workflow_id
            else None
        )
        return {
            "executed": False,
            "step_state": outcome.state.value,
            "reason": outcome.reason,
            "workflow_state": workflow_state,
        }

    # ── Verify. Independent of the executing handler and deterministic. ──
    try:
        verification = verify_step_result(step["tool_key"], outcome.result)
        verifier_error = None
    except Exception as error:  # noqa: BLE001
        # A verifier crash must not erase the execution record. The work
        # happened; the ledger already says so; this is a separate failure.
        verification = None
        verifier_error = type(error).__name__

    if verifier_error is not None:
        await _persist_step_result(
            db, owner_user_id=owner_user_id, step_id=step_id, result=outcome.result,
            verdict="VERIFIER_ERROR", duration_ms=outcome.duration_ms, trace_id=trace.trace_id,
        )
        await record_event(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
            event_type="VERIFIER_FAILED",
            summary=f"verifier raised {verifier_error}; execution evidence preserved",
            from_state=StepState.VERIFYING.value, to_state=StepState.FAILED.value,
            trace_id=trace.trace_id,
        )
        await transition_step(
            db, owner_user_id=owner_user_id, step_id=step_id,
            current=StepState.VERIFYING, nxt=StepState.FAILED,
        )
        workflow_state = await _aggregate_workflow(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id
        )
        return {
            "executed": True,
            "verified": False,
            "step_state": StepState.FAILED.value,
            "verifier_error": verifier_error,
            "workflow_state": workflow_state,
        }

    final = StepState.SUCCEEDED if verification.verdict is Verdict.PASS else StepState.FAILED
    digest = await _persist_step_result(
        db, owner_user_id=owner_user_id, step_id=step_id, result=outcome.result,
        verdict=verification.verdict.value, duration_ms=outcome.duration_ms,
        trace_id=trace.trace_id,
    )
    await record_event(
        db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
        event_type="STEP_VERIFIED" if final is StepState.SUCCEEDED else "STEP_REJECTED",
        summary=f"{verification.verdict.value}: {'; '.join(verification.reasons) or 'checks passed'}",
        detail={"checks_run": list(verification.checks_run), "result_digest": digest},
        from_state=StepState.VERIFYING.value, to_state=final.value,
        trace_id=trace.trace_id,
    )
    await transition_step(
        db, owner_user_id=owner_user_id, step_id=step_id,
        current=StepState.VERIFYING, nxt=final,
    )

    unlocked: list[str] = []
    if final is StepState.SUCCEEDED:
        unlocked = [
            str(dep)
            for dep in await unlock_dependants(
                db, owner_user_id=owner_user_id, workflow_id=workflow_id
            )
        ]

    workflow_state = await _aggregate_workflow(
        db, owner_user_id=owner_user_id, workflow_id=workflow_id
    )
    return {
        "executed": True,
        "verified": verification.verdict is Verdict.PASS,
        "verdict": verification.verdict.value,
        "reasons": list(verification.reasons),
        "step_state": final.value,
        "result_digest": digest,
        "unlocked": unlocked,
        "workflow_state": workflow_state,
        "trace_id": trace.trace_id,
    }
