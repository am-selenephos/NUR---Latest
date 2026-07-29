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

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.approvals import compute_call_version
from app.agentic.orchestrator import argument_digest, record_event
from app.agentic.redaction import redact_arguments


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


async def _locked_context(db: AsyncSession, owner_user_id: uuid.UUID, approval_id: uuid.UUID):
    """Lock approval, step and workflow together, in that order everywhere.

    A consistent lock order is what keeps two owners deciding concurrently from
    deadlocking each other.
    """
    approval = (
        await db.execute(
            text(
                "SELECT * FROM agent_approvals "
                "WHERE id = :id AND owner_user_id = :o FOR UPDATE"
            ),
            {"id": approval_id, "o": owner_user_id},
        )
    ).mappings().first()
    if approval is None:
        # 404 rather than 403: confirming a row exists but belongs to someone
        # else is itself a disclosure.
        raise DecisionRefused("approval not found", 404)

    step = (
        await db.execute(
            text("SELECT * FROM agent_steps WHERE id = :s AND owner_user_id = :o FOR UPDATE"),
            {"s": approval["step_id"], "o": owner_user_id},
        )
    ).mappings().first()
    workflow = (
        await db.execute(
            text(
                "SELECT * FROM agent_workflows WHERE id = :w AND owner_user_id = :o FOR UPDATE"
            ),
            {"w": approval["workflow_id"], "o": owner_user_id},
        )
    ).mappings().first()
    if step is None or workflow is None:
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
        if verdict == "EDIT":
            if edited_arguments is None:
                raise DecisionRefused("an edit must supply edited_arguments", 422)
            digest = argument_digest(
                approval["tool_key"], approval["tool_version"], edited_arguments
            )
            call_version = compute_call_version(
                int(workflow["plan_version"]),
                approval["tool_key"],
                approval["tool_version"],
                digest,
            )
            await db.execute(
                text(
                    "UPDATE agent_approvals SET decision = 'EDITED', decided_at = now(), "
                    "decided_note = :note, edited_arguments = CAST(:edited AS jsonb), "
                    "argument_digest = :digest, call_version = :cv, "
                    "redacted_arguments = CAST(:redacted AS jsonb) WHERE id = :id"
                ),
                {
                    "id": approval_id, "note": note,
                    "edited": json.dumps(edited_arguments),
                    "digest": digest, "cv": call_version,
                    "redacted": json.dumps(redact_arguments(edited_arguments)),
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

        await _invalidate_other_actionable(db, owner_user_id, step["id"], approval_id)
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

    workflow_state = (
        await db.execute(
            text(
                "SELECT CASE WHEN count(*) FILTER (WHERE state = 'FAILED') > 0 THEN 'FAILED' "
                "WHEN count(*) FILTER (WHERE state = 'WAITING_APPROVAL') > 0 "
                "THEN 'WAITING_APPROVAL' ELSE 'RUNNING' END "
                "FROM agent_steps WHERE workflow_id = :w"
            ),
            {"w": workflow["id"]},
        )
    ).scalar_one()
    await db.execute(
        text("UPDATE agent_workflows SET state = :st, updated_at = now() WHERE id = :w"),
        {"st": workflow_state, "w": workflow["id"]},
    )

    return DecisionResult(
        approval_id=approval_id,
        decision=verdict if verdict != "APPROVE" else "APPROVED",
        step_state=new_state,
        workflow_state=workflow_state,
        outbox_intent_id=intent_id,
    )
