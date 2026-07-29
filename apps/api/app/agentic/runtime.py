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

import datetime as dt
import inspect
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
    approval_id: uuid.UUID | None = None,
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
                denial_reason, duration_ms, trace_id, approval_id
            ) VALUES (
                :owner, :workflow, :step, :tool, :version, :risk, :digest,
                CAST(:args AS jsonb), :outcome, :denial, :duration, :trace, :approval
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
            # NULL for auto-run work; the authorising row for approved or edited
            # execution, so a durable effect can always be traced to the consent
            # that permitted it.
            "approval": approval_id,
        },
    )


async def _ensure_approval_row(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    step_id: uuid.UUID,
    tool_key: str,
    tool_version: str,
    arguments: dict,
    rationale: str,
    risk_class: str,
    reversible: bool,
    cost_ceiling_cents: int,
    expected_result: str | None = None,
    scope_summary: str | None = None,
    expires_at: "dt.datetime | None" = None,
) -> uuid.UUID:
    """Create exactly one actionable approval for this step, bound to this call.

    Previously this wrote neither plan_version nor call_version, so every insert
    violated ck_agent_approval_pending_bound and the runtime could not create an
    approval at all — the pause path was unreachable.

    Replacement is explicit rather than a caught unique violation. The index
    permits one PENDING row per step, so an existing pending approval for a
    *different* call must be invalidated first. Relying on the constraint to
    reject the insert would lose the old row's history and turn an ordinary
    re-plan into an error path.
    """
    import json

    from app.agentic.approvals import compute_call_version

    digest = argument_digest(tool_key, tool_version, arguments)

    # Lock the workflow so plan_version cannot move under us between read and
    # insert; the step lock keeps a concurrent worker from pausing it twice.
    plan_version = (
        await db.execute(
            text(
                "SELECT plan_version FROM agent_workflows "
                "WHERE id = :w AND owner_user_id = :o FOR UPDATE"
            ),
            {"w": workflow_id, "o": owner_user_id},
        )
    ).scalar_one()
    await db.execute(
        text("SELECT 1 FROM agent_steps WHERE id = :s AND owner_user_id = :o FOR UPDATE"),
        {"s": step_id, "o": owner_user_id},
    )

    call_version = compute_call_version(plan_version, tool_key, tool_version, digest)

    existing = (
        await db.execute(
            text(
                "SELECT id, call_version FROM agent_approvals "
                "WHERE step_id = :s AND owner_user_id = :o AND decision = 'PENDING' "
                "FOR UPDATE"
            ),
            {"s": step_id, "o": owner_user_id},
        )
    ).mappings().first()

    if existing is not None:
        if existing["call_version"] == call_version:
            # Same call, already asked. Idempotent: a redelivery must not stack
            # a second card in the inbox.
            return existing["id"]
        # A different call. Invalidate rather than delete: what NUR previously
        # asked for is part of the record.
        await db.execute(
            text(
                "UPDATE agent_approvals SET decision = 'INVALIDATED' "
                "WHERE id = :id AND owner_user_id = :o"
            ),
            {"id": existing["id"], "o": owner_user_id},
        )

    row = await db.execute(
        text(
            """
            INSERT INTO agent_approvals (
                owner_user_id, workflow_id, step_id, tool_key, tool_version,
                argument_digest, redacted_arguments, rationale, expected_result,
                risk_class, reversible, scope_summary, cost_ceiling_cents,
                decision, plan_version, call_version, expires_at
            ) VALUES (
                :owner, :workflow, :step, :tool, :version, :digest,
                CAST(:args AS jsonb), :rationale, :expected, :risk, :reversible,
                :scope, :ceiling, 'PENDING', :plan_version, :call_version, :expires
            )
            RETURNING id
            """
        ),
        {
            "owner": owner_user_id,
            "workflow": workflow_id,
            "step": step_id,
            "tool": tool_key,
            "version": tool_version,
            "digest": digest,
            "args": json.dumps(redact_arguments(arguments)),
            "rationale": rationale[:2000],
            "expected": expected_result,
            "risk": risk_class,
            "reversible": reversible,
            "scope": scope_summary,
            "ceiling": cost_ceiling_cents,
            "plan_version": plan_version,
            "call_version": call_version,
            "expires": expires_at,
        },
    )
    return row.scalar_one()



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
    plan_version: int = 1,
) -> StepOutcome:
    """Run one already-claimed step through the gate and the handler.

    This function does not claim. `run_step` is the only claim site in the
    system; a guarded second one here would still be a second one, and the
    guard is exactly the kind of flag that gets passed wrongly once and
    reintroduces double-claiming.

    Returns a StepOutcome rather than raising for expected refusals — a policy
    denial and a lost claim are both normal states of the system, and turning
    them into exceptions would make ordinary operation look like failure in the
    logs. Genuine faults still raise.
    """
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
            approval_id=approval.approval_id if approval else None,
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
        # A row that merely says APPROVED is not sufficient. The approval is
        # re-validated against the call about to run: tool, version, current
        # arguments, expiry and cost ceiling. This applies to R0 and R1 calls
        # that require approval exactly as it does to R2 — the protection
        # belongs to the decision, not to the risk class.
        held = False
        if approval is not None:
            import datetime as _dt

            from app.agentic.approvals import evaluate_resume

            # The effective payload is chosen *before* validation, not after.
            # Validating the original arguments against an EDITED approval's
            # digest can never match — the digest was recomputed from the edit —
            # so `held` was always false and the branch that applied the edit was
            # unreachable. The edited path existed only in the reading.
            effective_arguments = (
                dict(approval.edited_arguments)
                # `is not None`, not truthiness: an edit to {} is an intentional
                # empty payload, and treating it as "no edit" would silently run
                # the original arguments the owner replaced.
                if approval.decision is ApprovalDecision.EDITED
                and approval.edited_arguments is not None
                else arguments
            )

            resume = evaluate_resume(
                approval,
                tool_key=tool_key,
                tool_version=contract.version,
                arguments=effective_arguments,
                now=_dt.datetime.now(_dt.timezone.utc),
                estimated_cost_cents=contract.estimated_cost_cents,
                current_plan_version=plan_version,
            )
            held = resume.allowed
            if held:
                # The handler and the ledger both receive exactly what passed the
                # gate. Anything else would mean auditing a call that did not run.
                arguments = dict(resume.arguments or effective_arguments)
            else:
                await record_event(
                    db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
                    event_type="APPROVAL_REFUSED",
                    summary=f"{resume.refusal}: {resume.message}",
                    trace_id=trace.trace_id,
                )

        if not held:
            await _ensure_approval_row(
                db,
                owner_user_id=owner_user_id,
                workflow_id=workflow_id,
                step_id=step_id,
                tool_key=tool_key,
                tool_version=contract.version,
                arguments=arguments,
                rationale=verdict.reason,
                risk_class=contract.risk_class.value,
                reversible=contract.reversible,
                cost_ceiling_cents=contract.estimated_cost_cents,
            )
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
        # Only durable handlers re-check consent; read and draft handlers do not
        # accept an `approval` keyword and passing it blindly is a TypeError that
        # surfaces as a step failure rather than as the wiring bug it is.
        if approval is not None and "approval" in inspect.signature(handler).parameters:
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
            approval_id=approval.approval_id if approval else None,
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
        approval_id=approval.approval_id if approval else None,
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
    tool_key: str | None = None,
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

    from app.agentic.registry import UnknownToolError, spec as tool_spec

    payload = redact_arguments(result or {})
    digest = argument_digest("__result__", "1", payload)

    # Typed extraction from the tool's declared contract. Suffix matching on
    # "_id" previously classified every identifier as an artifact, so a plan id,
    # a research brief id and a genuine artifact id were indistinguishable in
    # the ledger — and only one of them was an artifact.
    artifact_ids: list[str] = []
    evidence_ids: list[str] = []
    entity_refs: list[dict[str, str]] = []
    try:
        declared = tool_spec(tool_key) if tool_key else None
    except UnknownToolError:
        declared = None
    if declared is not None and isinstance(payload, dict):
        for key in declared.artifact_ref_keys:
            value = payload.get(key)
            if isinstance(value, str):
                artifact_ids.append(value)
        for key in declared.evidence_ref_keys:
            value = payload.get(key)
            if isinstance(value, str):
                evidence_ids.append(value)
        for key, kind in declared.entity_refs:
            value = payload.get(key)
            if isinstance(value, str):
                entity_refs.append({"kind": kind, "id": value})

    manifest = {
        "keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "artifact_ids": artifact_ids,
        "evidence_ids": evidence_ids,
        "entity_refs": entity_refs,
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
                   evidence_ids = CAST(:evidence AS jsonb),
                   trace_id = :trace,
                   completed_at = now(),
                   updated_at = now()
             WHERE id = :step AND owner_user_id = :owner
            """
        ),
        {
            "result": json.dumps({"manifest": manifest, "output": payload}),
            "verdict": verdict,
            "artifacts": json.dumps(artifact_ids),
            "evidence": json.dumps(evidence_ids),
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
                  count(*) FILTER (WHERE state = 'NEEDS_REVISION') AS revising,
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
    elif row["revising"]:
        # Dependants stay BLOCKED: unlock_dependants only promotes when every
        # dependency is SUCCEEDED, so a revising step holds its subtree.
        state = "NEEDS_REVISION"
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
    trace: TraceContext,
    worker: str,
    within_scope: bool = True,
) -> dict[str, Any]:
    """The single top-level entry point. The runtime owns the claim.

    Policy and approval are resolved *after* the claim, never before. State read
    before claiming is state that may have changed by the time the step runs: an
    owner who revokes a policy or rejects an approval in that window would have
    had their decision ignored, because the worker was already holding a stale
    copy. Loading inside the claim closes that window.

    There is exactly one claim site in the system and it is inside
    `execute_step`. The worker sets the RLS context and calls this; it does not
    claim. Two claim sites meant a worker that claimed and a runtime that then
    refused because the step was no longer QUEUED — the defect this replaces.

    After execution the loop actually closes: verify, persist, transition to a
    terminal state, unlock dependants, and recompute the workflow's state.
    """
    from app.agentic.orchestrator import queue_ready_dependants, unlock_dependants
    from app.agentic.verifier import Verdict, verify_step_result

    from app.agentic.policy_store import load_policy, load_step_approval

    claim = await claim_step(
        db, owner_user_id=owner_user_id, step_id=step_id, worker_id=worker
    )
    if not claim.claimed:
        return {"executed": False, "step_state": "QUEUED", "reason": claim.reason}

    step = await _load_step(db, owner_user_id, step_id)
    if step is None:
        raise RuntimeRefusal("claimed a step that cannot be re-read; RLS context is wrong")

    # Scope for policy precedence comes from the workflow the claimed step
    # belongs to, so a Project policy can override an Orbit policy which
    # overrides the account default.
    scope = (
        await db.execute(
            text(
                "SELECT orbit_id, project_id, plan_version FROM agent_workflows "
                "WHERE id = :workflow AND owner_user_id = :owner"
            ),
            {"workflow": step["workflow_id"], "owner": owner_user_id},
        )
    ).mappings().first() or {}

    policy = await load_policy(
        db,
        owner_user_id=owner_user_id,
        orbit_id=scope.get("orbit_id"),
        project_id=scope.get("project_id"),
    )
    approval = await load_step_approval(
        db, owner_user_id=owner_user_id, step_id=step_id
    )

    outcome = await execute_step(
        db,
        owner_user_id=owner_user_id,
        step_id=step_id,
        policy=policy,
        trace=trace,
        worker=worker,
        approval=approval,
        within_scope=within_scope,
        plan_version=int(scope.get("plan_version") or 1),
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
            tool_key=step["tool_key"],
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

    # REVISE is not failure. An honest no-op completed correctly and simply did
    # not achieve the step's aim; calling that a system failure would make a
    # planning problem look like a defect and would stop a workflow that should
    # be re-planned. FAILED is reserved for results that are unusable.
    if verification.verdict is Verdict.PASS:
        final = StepState.SUCCEEDED
    elif verification.verdict is Verdict.REVISE:
        final = StepState.NEEDS_REVISION
    else:
        final = StepState.FAILED
    digest = await _persist_step_result(
        db, owner_user_id=owner_user_id, step_id=step_id, result=outcome.result,
        verdict=verification.verdict.value, duration_ms=outcome.duration_ms,
        trace_id=trace.trace_id, tool_key=step["tool_key"],
    )
    await record_event(
        db, owner_user_id=owner_user_id, workflow_id=workflow_id, step_id=step_id,
        event_type=(
            "STEP_VERIFIED" if final is StepState.SUCCEEDED
            else "STEP_NEEDS_REVISION" if final is StepState.NEEDS_REVISION
            else "STEP_REJECTED"
        ),
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
    queued: list[str] = []
    if final is StepState.SUCCEEDED:
        unlocked = [
            str(dep)
            for dep in await unlock_dependants(
                db, owner_user_id=owner_user_id, workflow_id=workflow_id
            )
        ]
        # READY is not runnable: claim_step only claims QUEUED. The scheduler
        # moves them and writes the dispatch intent in this same transaction, so
        # a rollback takes the intent with it.
        queued = [
            str(row["step_id"])
            for row in await queue_ready_dependants(
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
        "queued": queued,
        "workflow_state": workflow_state,
        "trace_id": trace.trace_id,
    }
