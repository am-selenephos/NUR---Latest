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
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agentic import registry
from app.agentic import lifecycle_service as lifecycle
from app.agentic.enums import ApprovalDecision
from app.agentic.lifecycle_schemas import (
    AgentPolicyPut,
    WorkflowCreateIn,
    WorkflowRetryIn,
    WorkflowStartIn,
)
from app.api.deps import Identity, Scoped, require_csrf, require_trusted_origin
from app.models.agentic import AgentApproval, AgentRunEvent
from app.services import rate_limit

router = APIRouter(prefix="/agentic", tags=["agentic"])


class ApprovalDecisionIn(BaseModel):
    """Every `seen_*` field is required.

    Digest equality alone cannot detect an identical call regenerated under a
    successor plan — that is precisely what call_version exists to catch. An
    optional binding field is one a client can omit and thereby skip the check.
    """

    decision: str = Field(pattern="^(APPROVE|EDIT|REJECT)$")
    seen_digest: str = Field(min_length=8)
    seen_plan_version: int = Field(ge=1)
    seen_call_version: str = Field(min_length=8)
    note: str | None = Field(default=None, max_length=2000)
    # `{}` is a meaningful edit; None means "not an edit".
    edited_arguments: dict | None = None


async def _raise_lifecycle_refusal(
    db: Scoped, refusal: lifecycle.LifecycleRefused
) -> NoReturn:
    await db.rollback()
    raise HTTPException(
        status_code=refusal.status_code,
        detail=refusal.detail(),
    ) from refusal


async def require_agentic_mutation_rate(request: Request, identity: Identity) -> None:
    owner_user_id, _ = identity
    ip = request.client.host if request.client else "unknown"
    allowed = await rate_limit.allow_agentic_mutation(
        request.app.state.redis,
        user_id=str(owner_user_id),
        ip=ip,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many Agent changes; try again shortly.")


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


@router.get("/policy")
async def get_policy(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    return await lifecycle.get_account_policy(db, owner_user_id=owner_user_id)


@router.put(
    "/policy",
    dependencies=[
        Depends(require_csrf),
        Depends(require_trusted_origin),
        Depends(require_agentic_mutation_rate),
    ],
)
async def put_policy(payload: AgentPolicyPut, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    try:
        result = await lifecycle.put_account_policy(
            db, owner_user_id=owner_user_id, payload=payload
        )
    except lifecycle.LifecycleRefused as refusal:
        await _raise_lifecycle_refusal(db, refusal)
    await db.commit()
    return result


@router.get("/workflows")
async def list_workflows(
    db: Scoped,
    identity: Identity,
    state: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> dict:
    owner_user_id, _ = identity
    try:
        return await lifecycle.list_workflows(
            db,
            owner_user_id=owner_user_id,
            state=state,
            limit=limit,
            cursor=cursor,
        )
    except lifecycle.LifecycleRefused as refusal:
        await _raise_lifecycle_refusal(db, refusal)


@router.post(
    "/workflows",
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(require_trusted_origin),
        Depends(require_agentic_mutation_rate),
    ],
)
async def create_workflow(
    payload: WorkflowCreateIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    try:
        result = await lifecycle.create_workflow(
            db, owner_user_id=owner_user_id, payload=payload
        )
    except lifecycle.LifecycleRefused as refusal:
        await _raise_lifecycle_refusal(db, refusal)
    await db.commit()
    return result


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    try:
        return await lifecycle.get_workflow(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id
        )
    except lifecycle.LifecycleRefused as refusal:
        await _raise_lifecycle_refusal(db, refusal)


@router.post(
    "/workflows/{workflow_id}/start",
    dependencies=[
        Depends(require_csrf),
        Depends(require_trusted_origin),
        Depends(require_agentic_mutation_rate),
    ],
)
async def start_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowStartIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    try:
        result = await lifecycle.start_workflow(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow_id,
            seen_plan_version=payload.seen_plan_version,
        )
    except lifecycle.LifecycleRefused as refusal:
        await _raise_lifecycle_refusal(db, refusal)
    await db.commit()
    return result


@router.post(
    "/workflows/{workflow_id}/cancel",
    dependencies=[
        Depends(require_csrf),
        Depends(require_trusted_origin),
        Depends(require_agentic_mutation_rate),
    ],
)
async def cancel_workflow(
    workflow_id: uuid.UUID,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    try:
        result = await lifecycle.cancel_workflow(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id
        )
    except lifecycle.LifecycleRefused as refusal:
        await _raise_lifecycle_refusal(db, refusal)
    await db.commit()
    return result


@router.post(
    "/workflows/{workflow_id}/retry",
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(require_trusted_origin),
        Depends(require_agentic_mutation_rate),
    ],
)
async def retry_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowRetryIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    try:
        result = await lifecycle.retry_workflow(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow_id,
            payload=payload,
        )
    except lifecycle.LifecycleRefused as refusal:
        await _raise_lifecycle_refusal(db, refusal)
    await db.commit()
    return result


@router.get("/workflows/{workflow_id}/events")
async def workflow_events(
    workflow_id: uuid.UUID,
    db: Scoped,
    identity: Identity,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict:
    owner_user_id, _ = identity
    try:
        await lifecycle.get_workflow(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id
        )
    except lifecycle.LifecycleRefused as refusal:
        await _raise_lifecycle_refusal(db, refusal)
    rows = (
        await db.execute(
            select(AgentRunEvent)
            .where(
                AgentRunEvent.workflow_id == workflow_id,
                AgentRunEvent.owner_user_id == owner_user_id,
                AgentRunEvent.sequence > after_sequence,
            )
            .order_by(AgentRunEvent.sequence)
            .limit(limit + 1)
        )
    ).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
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
        "next_after_sequence": rows[-1].sequence if has_more and rows else None,
        "provenance_label": "Append-only run ledger",
    }


@router.get("/approvals")
async def list_approvals(
    db: Scoped,
    identity: Identity,
    limit: int = Query(default=100, ge=1, le=100),
) -> dict:
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
            .limit(limit)
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
                # The whole binding, so a client can prove it decided on exactly
                # what it displayed — including the plan revision.
                "approval_id": str(r.id),
                "step_id": str(r.step_id) if r.step_id else None,
                "argument_digest": r.argument_digest,
                "plan_version": r.plan_version,
                "call_version": r.call_version,
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.post(
    "/approvals/{approval_id}/decide",
    dependencies=[
        Depends(require_csrf),
        Depends(require_trusted_origin),
        Depends(require_agentic_mutation_rate),
    ],
)
async def decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecisionIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    """Apply the owner's decision atomically.

    The decision, the step transition, the ledger event and the dispatch intent
    commit together. No broker call happens here — the intent row is the handoff.
    """
    from app.agentic.decisions import DecisionRefused, decide

    owner_user_id, _ = identity
    try:
        result = await decide(
            db,
            owner_user_id=owner_user_id,
            approval_id=approval_id,
            decision=payload.decision,
            seen_digest=payload.seen_digest,
            seen_plan_version=payload.seen_plan_version,
            seen_call_version=payload.seen_call_version,
            note=payload.note,
            edited_arguments=payload.edited_arguments,
        )
    except DecisionRefused as refusal:
        await db.rollback()
        raise HTTPException(status_code=refusal.status_code, detail=str(refusal)) from refusal

    await db.commit()
    return {
        "approval_id": str(result.approval_id),
        "decision": result.decision,
        "step_state": result.step_state,
        "workflow_state": result.workflow_state,
        "outbox_intent_id": str(result.outbox_intent_id) if result.outbox_intent_id else None,
    }
