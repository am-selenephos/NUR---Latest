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
        # No configured policy is not permission. SUGGEST, an R1 ceiling, and
        # zero capabilities — an owner who has never opened these settings has
        # granted nothing, so a capability-bearing tool cannot run at all.
        return OwnerPolicy(
            initiative_level=InitiativeLevel.SUGGEST,
            max_risk_class=RiskClass.R1_PRIVATE_DRAFT,
            granted_capabilities=frozenset(),
        )

    # Direct attribute access, not getattr with a default. A getattr fallback
    # on a required schema field silently produced an empty permission set for
    # every policy when the ORM did not map the column — which, with an
    # unconditional permission gate, denied every tool in the product. Failing
    # loudly at import or attribute time is the correct behaviour for a field
    # the schema guarantees.
    permitted = frozenset(chosen.permitted_tools or ())
    # auto_run is a strict subset of permitted: naming a tool for unattended use
    # cannot also permit it, or auto_run would quietly become a second
    # permission grant.
    auto_run = frozenset(chosen.auto_run_tools or ()) & permitted
    return OwnerPolicy(
        initiative_level=InitiativeLevel(chosen.initiative_level),
        max_risk_class=RiskClass(chosen.max_risk_class),
        permitted_tools=permitted,
        auto_run_tools=auto_run,
        denied_tools=frozenset(chosen.denied_tools or ()),
        # Capabilities derive from permitted tools only. Deriving them from
        # auto_run would mean a tool could be approved without the capability it
        # needs, and deriving from the legacy column would keep the split
        # decorative.
        granted_capabilities=capabilities_for(permitted),
        daily_budget_cents=chosen.daily_budget_cents,
    )


def capabilities_for(allowed_tools: frozenset[str]) -> frozenset[str]:
    """The exact union of capabilities required by the explicitly allowed tools.

    This replaces a fail-open that granted everything. The previous expression
    was `frozenset(allowed_tools) & KNOWN_CAPABILITIES or KNOWN_CAPABILITIES`,
    which evaluates as `(A & B) or C` — so whenever the intersection was empty
    it fell through to the full capability set. And `allowed_tools` holds tool
    *keys*, not capability names, so that intersection was empty almost always.
    The net effect was that nearly every policy silently granted every
    capability in the product, which is the exact escalation the capability
    system exists to prevent.

    Capabilities are now derived, never fallen back to:

      * an empty or missing allowlist grants nothing;
      * a tool key that resolves to no contract contributes nothing;
      * a capability a contract names but the known set does not is dropped, so
        a typo or an injected value cannot widen what a workflow may do.

    There is no branch in this function that can return KNOWN_CAPABILITIES.
    """
    from app.agentic.registry import UnknownToolError, contract

    granted: set[str] = set()
    for key in allowed_tools:
        try:
            tool = contract(key)
        except UnknownToolError:
            # An unrecognised tool grants nothing rather than being trusted.
            continue
        granted |= set(tool.required_capabilities)
    # Intersect, never union-with-fallback: an unknown capability name is
    # dropped instead of admitted.
    return frozenset(granted & KNOWN_CAPABILITIES)


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
