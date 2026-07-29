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

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.approvals import StoredApproval
from app.agentic.enums import ApprovalDecision, InitiativeLevel, RiskClass
from app.agentic.policy import OwnerPolicy
from app.agentic.tools import KNOWN_CAPABILITIES
from app.models.agentic import AgentApproval, AgentPolicy


class MultipleActionableApprovals(RuntimeError):
    """Corruption: one step, several live decisions. Never resolved silently."""


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

    window, zone = _quiet_hours(chosen.quiet_hours)
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
        # Read from the durable ledger, never carried in memory between runs. A
        # counter held in a worker process resets on restart and is wrong the
        # moment a second worker exists; the budget then silently stops binding.
        spent_today_cents=await daily_spend_cents(
            db, owner_user_id=owner_user_id, timezone_name=zone
        ),
        quiet_hours=window,
        timezone_name=zone,
    )


def _quiet_hours(raw: dict | None) -> tuple[tuple[int, int] | None, str]:
    """Read `{"start": 22, "end": 7, "tz": "Asia/Karachi"}` from the policy.

    Returns (window, zone). A malformed or absent window yields no quiet hours,
    but the zone is still returned so spend accounting has a day boundary to
    use. Hours outside 0-23 are dropped rather than clamped: clamping a typo
    into a valid hour invents a rule the owner never wrote.
    """
    zone = "UTC"
    if not isinstance(raw, dict):
        return None, zone

    candidate = raw.get("tz") or raw.get("timezone")
    if isinstance(candidate, str) and candidate.strip():
        # Validated here, once, rather than trusted downstream. The zone is
        # interpolated into `AT TIME ZONE` when spend is summed, and PostgreSQL
        # raises on an unrecognised name — so an owner with a typo in this jsonb
        # made `load_policy` throw, which fails *every* step execution for them.
        # A bad config value must degrade, not take the runtime down.
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(candidate.strip())
            zone = candidate.strip()
        except Exception:  # noqa: BLE001 - any malformed or unknown zone
            zone = "UTC"

    start, end = raw.get("start"), raw.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        return None, zone
    if not (0 <= start <= 23 and 0 <= end <= 23):
        return None, zone
    return (start, end), zone


async def daily_spend_cents(
    db: AsyncSession, *, owner_user_id: uuid.UUID, timezone_name: str = "UTC"
) -> int:
    """What this owner has already spent today, from `agent_tool_calls`.

    The authoritative record is the ledger of calls that actually happened, so
    the figure survives a restart and is consistent across concurrent workers.

    "Today" is a calendar day in the owner's own zone, computed by Postgres via
    `AT TIME ZONE` so the boundary moves with the owner rather than at UTC
    midnight. Retries do not double-charge because each `agent_tool_calls` row
    is one invocation: a duplicate delivery that loses its claim never reaches
    the handler and so never writes a row.

    Scoped to `owner_user_id`, so another owner's spend cannot consume this
    owner's budget — and RLS confines it to this owner regardless.
    """
    total = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(cost_cents), 0) FROM agent_tool_calls
                 WHERE owner_user_id = :owner
                   AND (created_at AT TIME ZONE :tz)::date
                       = (now() AT TIME ZONE :tz)::date
                """
            ),
            {"owner": owner_user_id, "tz": timezone_name},
        )
    ).scalar_one()
    return int(total or 0)


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
    """The actionable consent for this step, or nothing.

    Only APPROVED and EDITED are consent. A PENDING row is a question the owner
    has not answered — handing it to the execution gate as if it were an answer
    is the difference between asking and assuming. REJECTED, EXPIRED and
    INVALIDATED are history.

    More than one actionable row for a single step is corruption the uniqueness
    index is meant to prevent. Choosing the newest would quietly execute under
    whichever decision happened to sort first; this fails closed instead.
    """
    rows = (
        await db.execute(
            select(AgentApproval)
            .where(
                AgentApproval.owner_user_id == owner_user_id,
                AgentApproval.step_id == step_id,
                AgentApproval.decision.in_(
                    [ApprovalDecision.APPROVED.value, ApprovalDecision.EDITED.value]
                ),
            )
            .order_by(AgentApproval.created_at.desc())
        )
    ).scalars().all()

    if not rows:
        return None
    if len(rows) > 1:
        raise MultipleActionableApprovals(
            f"step {step_id} has {len(rows)} actionable approvals; refusing to choose"
        )

    row = rows[0]
    return StoredApproval(
        approval_id=row.id,
        tool_key=row.tool_key,
        tool_version=row.tool_version,
        argument_digest=row.argument_digest,
        redacted_arguments=row.redacted_arguments,
        decision=ApprovalDecision(row.decision),
        cost_ceiling_cents=row.cost_ceiling_cents,
        expires_at=row.expires_at,
        edited_arguments=row.edited_arguments,
        plan_version=row.plan_version,
        call_version=row.call_version,
    )
