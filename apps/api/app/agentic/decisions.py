"""The owner's decision, applied atomically.

Everything that makes an approval real happens in one transaction: the decision,
the step transition, the ledger event and the dispatch intent. Splitting them
means a crash can leave a step QUEUED with nothing coming, or an APPROVED row
whose step never moved.

No Celery publish happens here. The intent row is the handoff; the dispatcher
reads what was committed.

`seen_*` are required, not optional. Digest equality alone cannot detect an
identical call regenerated under a successor plan — that is exactly what
call_version exists to catch, and an owner deciding on a card rendered before a
re-plan must be told rather than silently obeyed.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic import registry
from app.agentic.aggregate import aggregate_workflow
from app.agentic.approvals import StoredApproval, apply_edit, compute_call_version
from app.agentic.enums import ApprovalDecision
from app.agentic.input_schemas import validate_arguments
from app.agentic.orchestrator import record_event


class DecisionRefused(RuntimeError):
    """A decision that cannot be applied. Carries an HTTP status for the API."""

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DecisionResult:
    approval_id: uuid.UUID
    decision: str
    step_state: str
    workflow_state: str | None
    outbox_intent_id: uuid.UUID | None


# The one lock order every approval path uses: workflow, then step, then the
# step's approvals ordered by id. `_ensure_approval_row` acquires the same
# sequence. Two different orders across two paths is a deadlock waiting for
# concurrency, and a docstring claiming consistency does not create it.
async def _locked_context(db: AsyncSession, owner_user_id: uuid.UUID, approval_id: uuid.UUID):
    """Resolve ids without locking, then acquire locks in canonical order."""
    ids = (
        await db.execute(
            text(
                "SELECT workflow_id, step_id FROM agent_approvals "
                "WHERE id = :id AND owner_user_id = :o"
            ),
            {"id": approval_id, "o": owner_user_id},
        )
    ).mappings().first()
    if ids is None:
        # 404 rather than 403: confirming a row exists but belongs to someone
        # else is itself a disclosure.
        raise DecisionRefused("approval not found", 404)

    workflow = (
        await db.execute(
            text(
                "SELECT * FROM agent_workflows WHERE id = :w AND owner_user_id = :o FOR UPDATE"
            ),
            {"w": ids["workflow_id"], "o": owner_user_id},
        )
    ).mappings().first()
    step = (
        await db.execute(
            text("SELECT * FROM agent_steps WHERE id = :s AND owner_user_id = :o FOR UPDATE"),
            {"s": ids["step_id"], "o": owner_user_id},
        )
    ).mappings().first()
    # Every approval for this step, ordered by id — so a concurrent creation and
    # a concurrent decision contend in the same sequence.
    approvals = (
        await db.execute(
            text(
                "SELECT * FROM agent_approvals WHERE step_id = :s AND owner_user_id = :o "
                "ORDER BY id FOR UPDATE"
            ),
            {"s": ids["step_id"], "o": owner_user_id},
        )
    ).mappings().all()

    # Reloaded after locking: values read before the lock may be stale.
    approval = next((row for row in approvals if row["id"] == approval_id), None)
    if step is None or workflow is None or approval is None:
        raise DecisionRefused("approval is not bound to a live step and workflow", 409)
    return approval, step, workflow


def _check_binding(approval, workflow, *, seen_digest, seen_plan_version, seen_call_version):
    if approval["decision"] != "PENDING":
        raise DecisionRefused(
            f"already {approval['decision'].lower()}; a decision cannot be replaced", 409
        )
    if approval["argument_digest"] != seen_digest:
        raise DecisionRefused(
            "this request changed after it was shown to you; review it again", 409
        )
    if int(seen_plan_version) != int(approval["plan_version"]):
        raise DecisionRefused("the plan was revised after this card was rendered", 409)
    if approval["call_version"] != seen_call_version:
        raise DecisionRefused("this card no longer describes the current call", 409)
    if int(workflow["plan_version"]) != int(approval["plan_version"]):
        # The identical-call-under-a-successor-plan case: digest matches, and it
        # is still not the same decision.
        raise DecisionRefused(
            "the workflow was re-planned; this approval no longer applies", 409
        )


def _validate_before_queue(approval, step, workflow) -> None:
    """Everything APPROVE and EDIT must both be true before anything queues.

    Digest/plan_version/call_version equality against what the client saw is
    `_check_binding`'s job; this is the independent check against what is
    *currently* true regardless of what the client believes — expiry, the
    step's own tool identity, whatever the registry serves right now, whether
    a handler even exists to run it, the cost ceiling, and a call_version
    recomputed fresh rather than trusted from the stored row.
    """
    now = dt.datetime.now(dt.timezone.utc)
    if approval["expires_at"] is not None and now >= approval["expires_at"]:
        raise DecisionRefused("the approval expired; ask again rather than assuming consent persists", 409)

    if step["tool_key"] != approval["tool_key"] or step["tool_version"] != approval["tool_version"]:
        raise DecisionRefused(
            "the step's tool no longer matches what this approval was written for", 409
        )

    try:
        current_contract = registry.contract(approval["tool_key"])
    except LookupError as exc:
        raise DecisionRefused(f"{approval['tool_key']} is no longer a known tool", 409) from exc

    if current_contract.version != approval["tool_version"]:
        raise DecisionRefused(
            f"the registry now serves {approval['tool_key']} v{current_contract.version}, "
            f"not v{approval['tool_version']} this approval was written for", 409,
        )

    if not registry.is_bound(approval["tool_key"]):
        raise DecisionRefused(f"{approval['tool_key']} has no bound handler", 409)

    if (
        approval["cost_ceiling_cents"]
        and current_contract.estimated_cost_cents > approval["cost_ceiling_cents"]
    ):
        raise DecisionRefused(
            f"{current_contract.estimated_cost_cents}c exceeds the approved ceiling of "
            f"{approval['cost_ceiling_cents']}c", 409,
        )

    expected_call_version = compute_call_version(
        int(workflow["plan_version"]), approval["tool_key"], approval["tool_version"],
        approval["argument_digest"],
    )
    if expected_call_version != approval["call_version"]:
        raise DecisionRefused(
            "this approval's call_version no longer matches its own recorded plan_version, "
            "tool and digest; it cannot be trusted", 409,
        )


async def _invalidate_other_actionable(db, owner_user_id, step_id, keep_id) -> None:
    """One actionable consent per step. A replacement invalidates its
    predecessor rather than sitting beside it."""
    await db.execute(
        text(
            "UPDATE agent_approvals SET decision = 'INVALIDATED' "
            "WHERE owner_user_id = :o AND step_id = :s AND id <> :keep "
            "AND decision IN ('APPROVED', 'EDITED')"
        ),
        {"o": owner_user_id, "s": step_id, "keep": keep_id},
    )


async def _queue_step_with_intent(db, *, owner_user_id, workflow_id, step_id, attempt) -> uuid.UUID:
    await db.execute(
        text(
            "UPDATE agent_steps SET state = 'QUEUED', queued_at = now(), updated_at = now() "
            "WHERE id = :s AND owner_user_id = :o AND state = 'WAITING_APPROVAL'"
        ),
        {"s": step_id, "o": owner_user_id},
    )
    row = await db.execute(
        text(
            """
            INSERT INTO agent_dispatch_outbox (
                owner_user_id, workflow_id, step_id, dispatch_key, state
            ) VALUES (:o, :w, :s, :key, 'RETRYABLE')
            ON CONFLICT (dispatch_key) DO NOTHING
            RETURNING id
            """
        ),
        {"o": owner_user_id, "w": workflow_id, "s": step_id, "key": f"{step_id}:{attempt}"},
    )
    existing = row.scalar_one_or_none()
    if existing is not None:
        return existing
    # A repeated decision must not create a second intent.
    return (
        await db.execute(
            text("SELECT id FROM agent_dispatch_outbox WHERE dispatch_key = :key"),
            {"key": f"{step_id}:{attempt}"},
        )
    ).scalar_one()


async def decide(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    approval_id: uuid.UUID,
    decision: str,
    seen_digest: str,
    seen_plan_version: int,
    seen_call_version: str,
    note: str | None = None,
    edited_arguments: dict | None = None,
) -> DecisionResult:
    """Apply APPROVE, EDIT or REJECT in one transaction."""
    approval, step, workflow = await _locked_context(db, owner_user_id, approval_id)
    _check_binding(
        approval, workflow,
        seen_digest=seen_digest,
        seen_plan_version=seen_plan_version,
        seen_call_version=seen_call_version,
    )
    if step["state"] != "WAITING_APPROVAL":
        raise DecisionRefused(f"step is {step['state']}, not awaiting approval", 409)

    verdict = decision.upper()
    intent_id: uuid.UUID | None = None

    if verdict == "REJECT":
        await db.execute(
            text(
                "UPDATE agent_approvals SET decision = 'REJECTED', decided_at = now(), "
                "decided_note = :note WHERE id = :id"
            ),
            {"id": approval_id, "note": note},
        )
        # CANCELLED is the state machine's explicit non-runnable terminal for a
        # step the owner stopped. Dependants stay BLOCKED because
        # unlock_dependants only promotes on SUCCEEDED.
        await db.execute(
            text(
                "UPDATE agent_steps SET state = 'CANCELLED', completed_at = now(), "
                "updated_at = now() WHERE id = :s AND state = 'WAITING_APPROVAL'"
            ),
            {"s": step["id"]},
        )
        await record_event(
            db, owner_user_id=owner_user_id, workflow_id=workflow["id"], step_id=step["id"],
            event_type="APPROVAL_REJECTED", summary=note or "owner rejected the request",
            from_state="WAITING_APPROVAL", to_state="CANCELLED", actor="OWNER",
        )
        new_state = "CANCELLED"

    elif verdict in ("APPROVE", "EDIT"):
        # Independent of what the client saw: expiry, the step's own tool
        # identity, whatever the registry currently serves, whether a handler
        # is even bound, the cost ceiling, and a freshly recomputed
        # call_version. All of this runs before anything mutates.
        _validate_before_queue(approval, step, workflow)

        if verdict == "EDIT":
            if edited_arguments is None:
                raise DecisionRefused("an edit must supply edited_arguments", 422)
            schema_problems = validate_arguments(approval["tool_key"], edited_arguments)
            if schema_problems:
                raise DecisionRefused(
                    "invalid edited_arguments: " + "; ".join(schema_problems), 422
                )

        # Invalidate first. Promoting before clearing an older actionable row
        # trips uq_agent_approval_one_actionable and aborts the transaction
        # before the invalidation can run.
        await _invalidate_other_actionable(db, owner_user_id, step["id"], approval_id)

        if verdict == "EDIT":
            # `apply_edit` owns what an edit *means*: a new binding, with the
            # digest and call_version recomputed from the edited payload and the
            # decision's identity, expiry and ceiling preserved. This used to be
            # reimplemented inline here, which left `apply_edit` with seven tests
            # and no production caller — so those tests proved a helper the
            # product did not use, while the shipped path was a second
            # implementation free to drift from it.
            stored = StoredApproval(
                approval_id=approval_id,
                tool_key=approval["tool_key"],
                tool_version=approval["tool_version"],
                argument_digest=approval["argument_digest"],
                redacted_arguments=approval["redacted_arguments"],
                decision=ApprovalDecision(approval["decision"]),
                cost_ceiling_cents=approval["cost_ceiling_cents"],
                expires_at=approval["expires_at"],
                plan_version=int(approval["plan_version"]),
                call_version=approval["call_version"],
            )
            edited = apply_edit(
                stored, edited_arguments, plan_version=int(workflow["plan_version"])
            )
            await db.execute(
                text(
                    "UPDATE agent_approvals SET decision = 'EDITED', decided_at = now(), "
                    "decided_note = :note, edited_arguments = CAST(:edited AS jsonb), "
                    "argument_digest = :digest, call_version = :cv, "
                    "plan_version = :plan_version, "
                    "redacted_arguments = CAST(:redacted AS jsonb) WHERE id = :id"
                ),
                {
                    "id": approval_id, "note": note,
                    "edited": json.dumps(edited.edited_arguments),
                    "digest": edited.argument_digest, "cv": edited.call_version,
                    "plan_version": edited.plan_version,
                    "redacted": json.dumps(edited.redacted_arguments),
                },
            )
            event = "APPROVAL_EDITED"
        else:
            await db.execute(
                text(
                    "UPDATE agent_approvals SET decision = 'APPROVED', decided_at = now(), "
                    "decided_note = :note WHERE id = :id"
                ),
                {"id": approval_id, "note": note},
            )
            event = "APPROVAL_APPROVED"

        intent_id = await _queue_step_with_intent(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow["id"],
            step_id=step["id"],
            attempt=int(step["attempt"]),
        )
        await record_event(
            db, owner_user_id=owner_user_id, workflow_id=workflow["id"], step_id=step["id"],
            event_type=event, summary=note or "owner decision recorded",
            from_state="WAITING_APPROVAL", to_state="QUEUED", actor="OWNER",
        )
        new_state = "QUEUED"
    else:
        raise DecisionRefused("decision must be APPROVE, EDIT or REJECT", 422)

    # One aggregate, shared with the runtime and recovery — not a second
    # implementation of the same CASE statement to drift out of sync with it.
    workflow_state = await aggregate_workflow(
        db, owner_user_id=owner_user_id, workflow_id=workflow["id"]
    )

    return DecisionResult(
        approval_id=approval_id,
        decision=verdict if verdict != "APPROVE" else "APPROVED",
        step_state=new_state,
        workflow_state=workflow_state,
        outbox_intent_id=intent_id,
    )
