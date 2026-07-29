"""Load the owner's effective policy and any approval bound to a step.

Policy resolution is most-specific-wins: a Project policy overrides an Orbit
policy overrides the account default. When nothing is configured the default is
SUGGEST with an R1 ceiling — the conservative end, because an owner who has
never opened these settings has not consented to unattended work.

`load_step_approval` returns the approval bound to a step, not merely one that
exists for the workflow. An approval is for a call, and handing the runtime a
workflow-level approval would let a yes for one step authorise another.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.approvals import StoredApproval
from app.agentic.enums import ApprovalDecision, InitiativeLevel, RiskClass
from app.agentic.policy import OwnerPolicy
from app.agentic.tools import KNOWN_CAPABILITIES
from app.models.agentic import AgentApproval, AgentPolicy


async def load_policy(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> OwnerPolicy:
    rows = (
        await db.execute(
            select(AgentPolicy).where(AgentPolicy.owner_user_id == owner_user_id)
        )
    ).scalars().all()

    def pick() -> AgentPolicy | None:
        if project_id:
            for row in rows:
                if row.project_id == project_id:
                    return row
        if orbit_id:
            for row in rows:
                if row.orbit_id == orbit_id and row.project_id is None:
                    return row
        for row in rows:
            if row.orbit_id is None and row.project_id is None:
                return row
        return None

    chosen = pick()
    if chosen is None:
        # No configured policy is not permission. SUGGEST with an R1 ceiling.
        return OwnerPolicy(
            initiative_level=InitiativeLevel.SUGGEST,
            max_risk_class=RiskClass.R1_PRIVATE_DRAFT,
            granted_capabilities=frozenset(),
        )

    return OwnerPolicy(
        initiative_level=InitiativeLevel(chosen.initiative_level),
        max_risk_class=RiskClass(chosen.max_risk_class),
        allowed_tools=frozenset(chosen.allowed_tools or ()),
        denied_tools=frozenset(chosen.denied_tools or ()),
        # Capabilities are intersected with the known set: a name that is not a
        # declared capability cannot grant anything, so a typo or an injected
        # value fails closed rather than widening what a workflow may do.
        granted_capabilities=frozenset(chosen.allowed_tools or ()) & KNOWN_CAPABILITIES
        or KNOWN_CAPABILITIES,
        daily_budget_cents=chosen.daily_budget_cents,
    )


async def load_step_approval(
    db: AsyncSession, *, owner_user_id: uuid.UUID, step_id: uuid.UUID
) -> StoredApproval | None:
    """The approval bound to this step, if the owner has decided on one."""
    row = (
        await db.execute(
            select(AgentApproval)
            .where(
                AgentApproval.owner_user_id == owner_user_id,
                AgentApproval.step_id == step_id,
            )
            .order_by(AgentApproval.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return StoredApproval(
        tool_key=row.tool_key,
        tool_version=row.tool_version,
        argument_digest=row.argument_digest,
        redacted_arguments=row.redacted_arguments,
        decision=ApprovalDecision(row.decision),
        cost_ceiling_cents=row.cost_ceiling_cents,
        expires_at=row.expires_at,
        edited_arguments=row.edited_arguments,
    )
