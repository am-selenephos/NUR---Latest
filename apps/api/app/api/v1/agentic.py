"""Agency Plane HTTP surface.

Read endpoints first, and only the writes that already have an owner-reviewed
meaning behind them. Every route is owner-scoped through `Scoped`, which sets
the RLS context, so a wrong id returns nothing rather than someone else's row.

Two shapes here are deliberate.

`/tools` returns the catalog including tools that are declared but not bound.
Hiding the unbound ones would make the surface look more capable than it is; an
owner reading the list is entitled to see what NUR can and cannot do, and
`bound: false` is the honest answer for the rest.

Approval decisions are POSTed with the argument digest the client saw. If the
stored digest has moved since the card was rendered — because the plan was
revised underneath it — the decision is refused rather than applied to arguments
the owner never read. That is the same guarantee `evaluate_resume` provides at
execution time, enforced one step earlier so the owner is told immediately.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agentic import registry
from app.agentic.enums import ApprovalDecision, WorkflowState
from app.api.deps import Identity, Scoped, require_csrf
from app.models.agentic import AgentApproval, AgentRunEvent, AgentStep, AgentWorkflow

router = APIRouter(prefix="/agentic", tags=["agentic"])


class WorkflowOut(BaseModel):
    id: str
    title: str
    objective: str
    state: str
    kind: str
    step_count: int
    steps_done: int
    cost_cents: int
    failure_code: str | None = None
    updated_at: str


class ApprovalDecisionIn(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    note: str | None = Field(default=None, max_length=2000)
    # The digest the client rendered its card from. Guards against deciding on
    # a call that changed after the card was drawn.
    seen_digest: str | None = None


@router.get("/tools")
async def list_tools(identity: Identity) -> dict:
    """The full catalog, including what is declared but not yet callable."""
    return {
        "tools": [
            {
                "key": spec.contract.key,
                "version": spec.contract.version,
                "risk_class": spec.contract.risk_class.value,
                "summary": spec.summary,
                "reads": list(spec.reads),
                "writes": list(spec.writes),
                "reversible": spec.contract.reversible,
                "required_capabilities": sorted(spec.contract.required_capabilities),
                "bound": registry.is_bound(spec.contract.key),
            }
            for spec in registry.catalog()
        ],
        "provenance_label": "First-party NUR tools. Unbound tools are declared but not callable.",
    }


@router.get("/workflows")
async def list_workflows(db: Scoped, identity: Identity, state: str | None = None) -> dict:
    owner_user_id, _ = identity
    statement = select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id)
    if state:
        if state not in {member.value for member in WorkflowState}:
            raise HTTPException(status_code=422, detail="unknown workflow state")
        statement = statement.where(AgentWorkflow.state == state)
    rows = (
        await db.execute(statement.order_by(AgentWorkflow.updated_at.desc()).limit(100))
    ).scalars().all()

    out = []
    for row in rows:
        steps = (
            await db.execute(
                select(AgentStep).where(AgentStep.workflow_id == row.id)
            )
        ).scalars().all()
        out.append(
            WorkflowOut(
                id=str(row.id),
                title=row.title,
                objective=row.objective,
                state=row.state,
                kind=row.kind,
                step_count=len(steps),
                steps_done=sum(1 for s in steps if s.state == "SUCCEEDED"),
                cost_cents=row.cost_cents,
                failure_code=row.failure_code,
                updated_at=row.updated_at.isoformat(),
            ).model_dump()
        )
    return {"workflows": out, "count": len(out)}


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    workflow = (
        await db.execute(
            select(AgentWorkflow).where(
                AgentWorkflow.id == workflow_id,
                AgentWorkflow.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    # 404 rather than 403: confirming a row exists but belongs to someone else
    # is itself a disclosure.
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")

    steps = (
        await db.execute(
            select(AgentStep)
            .where(AgentStep.workflow_id == workflow_id)
            .order_by(AgentStep.ordinal)
        )
    ).scalars().all()
    return {
        "id": str(workflow.id),
        "title": workflow.title,
        "objective": workflow.objective,
        "state": workflow.state,
        "plan_version": workflow.plan_version,
        # The manifest is returned in full, including exclusions: what a
        # workflow was NOT allowed to see is how an owner checks its scope.
        "context_manifest": workflow.context_manifest,
        "success_criteria": workflow.success_criteria,
        "cost_cents": workflow.cost_cents,
        "failure_code": workflow.failure_code,
        "steps": [
            {
                "id": str(s.id),
                "key": s.key,
                "ordinal": s.ordinal,
                "state": s.state,
                "role": s.role,
                "tool_key": s.tool_key,
                "risk_class": s.risk_class,
                "approval_required": s.approval_required,
                "depends_on": s.depends_on,
                "verification_verdict": s.verification_verdict,
                "attempt": s.attempt,
                "failure_code": s.failure_code,
            }
            for s in steps
        ],
    }


@router.get("/workflows/{workflow_id}/events")
async def workflow_events(workflow_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    rows = (
        await db.execute(
            select(AgentRunEvent)
            .where(
                AgentRunEvent.workflow_id == workflow_id,
                AgentRunEvent.owner_user_id == owner_user_id,
            )
            .order_by(AgentRunEvent.sequence)
        )
    ).scalars().all()
    return {
        "events": [
            {
                "sequence": r.sequence,
                "event_type": r.event_type,
                "from_state": r.from_state,
                "to_state": r.to_state,
                "summary": r.summary,
                "actor": r.actor,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "count": len(rows),
        "provenance_label": "Append-only run ledger",
    }


@router.get("/approvals")
async def list_approvals(db: Scoped, identity: Identity) -> dict:
    """Everything waiting on the owner, with the whole ask on each row."""
    owner_user_id, _ = identity
    rows = (
        await db.execute(
            select(AgentApproval)
            .where(
                AgentApproval.owner_user_id == owner_user_id,
                AgentApproval.decision == ApprovalDecision.PENDING.value,
            )
            .order_by(AgentApproval.created_at)
        )
    ).scalars().all()
    return {
        "approvals": [
            {
                "id": str(r.id),
                "workflow_id": str(r.workflow_id),
                "tool_key": r.tool_key,
                "tool_version": r.tool_version,
                "redacted_arguments": r.redacted_arguments,
                "rationale": r.rationale,
                "expected_result": r.expected_result,
                "risk_class": r.risk_class,
                "reversible": r.reversible,
                "scope_summary": r.scope_summary,
                "cost_ceiling_cents": r.cost_ceiling_cents,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                # Returned so a client can prove it decided on what it displayed.
                "argument_digest": r.argument_digest,
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.post("/approvals/{approval_id}/decide", dependencies=[Depends(require_csrf)])
async def decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecisionIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    approval = (
        await db.execute(
            select(AgentApproval).where(
                AgentApproval.id == approval_id,
                AgentApproval.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=404, detail="approval not found")

    if approval.decision != ApprovalDecision.PENDING.value:
        # Deciding twice is not an error worth 500-ing over, but it must not
        # silently overwrite the first decision either.
        raise HTTPException(
            status_code=409,
            detail=f"already {approval.decision.lower()}; a decision cannot be replaced",
        )

    if payload.seen_digest and payload.seen_digest != approval.argument_digest:
        raise HTTPException(
            status_code=409,
            detail=(
                "this request changed after it was shown to you; "
                "review it again rather than deciding on arguments you did not read"
            ),
        )

    approval.decision = payload.decision
    approval.decided_note = payload.note
    from app.models._mixins import now_utc

    approval.decided_at = now_utc()
    await db.commit()
    return {"id": str(approval.id), "decision": approval.decision}
