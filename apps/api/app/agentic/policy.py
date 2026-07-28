"""The gate every tool call passes through.

One pure function decides whether a call runs, pauses for the owner, or is
refused. Pure on purpose: this is the component where a subtle mistake becomes
NUR doing something to a person's life that they never agreed to, and a function
with no I/O can be exhaustively tested against every combination of risk class
and initiative level rather than spot-checked.

Two rules are absolute and deliberately not expressible as configuration:

  * R3 (external) and R4 (irreversible) can never auto-run. No initiative level,
    no allowlist entry and no budget grants them. The owner raising initiative
    to its maximum buys faster *preparation*, never unattended external action.

  * Unknown anything fails closed. An unrecognised tool, an unparseable risk
    class or a missing policy denies. The alternative — treating "I don't
    recognise this" as permission — is how capability escalation happens.

Everything else is the owner's to configure.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum

from app.agentic.enums import InitiativeLevel, RiskClass


class Decision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


# Ordering lets "max risk" comparisons be a simple index lookup rather than a
# chain of conditionals that can be reordered wrongly during a refactor.
RISK_ORDER: tuple[RiskClass, ...] = (
    RiskClass.R0_READ_ONLY,
    RiskClass.R1_PRIVATE_DRAFT,
    RiskClass.R2_DURABLE_PRIVATE,
    RiskClass.R3_EXTERNAL,
    RiskClass.R4_IRREVERSIBLE,
)

INITIATIVE_ORDER: tuple[InitiativeLevel, ...] = (
    InitiativeLevel.OFF,
    InitiativeLevel.SUGGEST,
    InitiativeLevel.PREPARE,
    InitiativeLevel.INTERNAL,
    InitiativeLevel.CONNECTED,
    InitiativeLevel.DELEGATED,
)

# The highest risk each initiative level may run *without asking*. Note that no
# level reaches R3: CONNECTED means "prepare external actions and pause", not
# "send things". DELEGATED is reserved and currently grants nothing beyond
# INTERNAL, because the scoping work it needs does not exist yet.
AUTO_RUN_CEILING: dict[InitiativeLevel, RiskClass | None] = {
    InitiativeLevel.OFF: None,
    InitiativeLevel.SUGGEST: RiskClass.R0_READ_ONLY,
    InitiativeLevel.PREPARE: RiskClass.R1_PRIVATE_DRAFT,
    InitiativeLevel.INTERNAL: RiskClass.R2_DURABLE_PRIVATE,
    InitiativeLevel.CONNECTED: RiskClass.R2_DURABLE_PRIVATE,
    InitiativeLevel.DELEGATED: RiskClass.R2_DURABLE_PRIVATE,
}

# R4 is not shippable yet. Kept as an explicit constant so enabling it is a
# visible code change with a test that has to be updated, not a config edit.
R4_ENABLED = False


@dataclass(frozen=True)
class ToolContract:
    key: str
    version: str
    risk_class: RiskClass
    required_capabilities: frozenset[str] = frozenset()
    estimated_cost_cents: int = 0
    reversible: bool = True


@dataclass(frozen=True)
class OwnerPolicy:
    initiative_level: InitiativeLevel = InitiativeLevel.SUGGEST
    max_risk_class: RiskClass = RiskClass.R1_PRIVATE_DRAFT
    allowed_tools: frozenset[str] = frozenset()
    denied_tools: frozenset[str] = frozenset()
    granted_capabilities: frozenset[str] = frozenset()
    daily_budget_cents: int = 0
    spent_today_cents: int = 0
    quiet_hours: tuple[int, int] | None = None


@dataclass(frozen=True)
class PolicyVerdict:
    decision: Decision
    reason: str
    # Populated when the decision is DENY or REQUIRE_APPROVAL, so the surface can
    # say what would change the answer instead of only that it said no.
    remedy: str | None = None
    denied_capabilities: frozenset[str] = field(default_factory=frozenset)


def _risk_rank(risk: RiskClass) -> int:
    return RISK_ORDER.index(risk)


def evaluate(
    tool: ToolContract,
    policy: OwnerPolicy,
    *,
    now: dt.datetime | None = None,
    within_scope: bool = True,
) -> PolicyVerdict:
    """Decide whether one tool call may run, must ask, or is refused.

    Order matters. Denials that are about *permission* are checked before
    denials that are about *timing or budget*, so an owner is never told "not
    enough budget" for something they were never allowed to do — that would be
    a misleading remedy and would leak the shape of the capability system.
    """
    # 1. Explicit denial beats every other setting, including an allowlist entry.
    if tool.key in policy.denied_tools:
        return PolicyVerdict(
            Decision.DENY,
            f"{tool.key} is on the owner's denied list.",
            remedy="Remove it from denied tools to reconsider.",
        )

    # 2. Scope. A call that reaches outside the workflow's declared context is
    #    refused regardless of risk — this is the cross-owner and cross-orbit
    #    boundary, not a preference.
    if not within_scope:
        return PolicyVerdict(
            Decision.DENY,
            "The call reaches outside the workflow's declared context scope.",
            remedy="Re-plan the step inside the approved scope.",
        )

    # 3. Capabilities. Missing capability is escalation, never an approval prompt:
    #    asking the owner to approve a capability the workflow was not granted
    #    would turn the approval inbox into an escalation vector.
    missing = tool.required_capabilities - policy.granted_capabilities
    if missing:
        return PolicyVerdict(
            Decision.DENY,
            f"{tool.key} requires capabilities that were not granted: {sorted(missing)}.",
            remedy="Grant the capability on the workflow before planning this step.",
            denied_capabilities=frozenset(missing),
        )

    # 4. R4 is disabled at the code level.
    if tool.risk_class is RiskClass.R4_IRREVERSIBLE and not R4_ENABLED:
        return PolicyVerdict(
            Decision.DENY,
            "Irreversible actions (R4) are not enabled in this build.",
            remedy=None,
        )

    # 5. The owner's own risk ceiling.
    if _risk_rank(tool.risk_class) > _risk_rank(policy.max_risk_class):
        return PolicyVerdict(
            Decision.DENY,
            f"{tool.risk_class} exceeds the owner's ceiling of {policy.max_risk_class}.",
            remedy="Raise the maximum risk class for this Orbit or Project.",
        )

    # 6. Initiative OFF means no background agency at all. A read-only call is
    #    still agency if NUR initiated it.
    if policy.initiative_level is InitiativeLevel.OFF:
        return PolicyVerdict(
            Decision.DENY,
            "Initiative is OFF for this scope.",
            remedy="Set initiative to at least SUGGEST.",
        )

    # 7. Budget. Checked after permission so the remedy is never misleading.
    projected = policy.spent_today_cents + tool.estimated_cost_cents
    if policy.daily_budget_cents and projected > policy.daily_budget_cents:
        return PolicyVerdict(
            Decision.DENY,
            f"Would spend {projected}c against a {policy.daily_budget_cents}c daily budget.",
            remedy="Raise the daily budget or wait for the next day.",
        )

    # 8. External and irreversible always ask, whatever the initiative level.
    #    This is the rule that keeps "no unapproved external action" structural.
    if tool.risk_class in (RiskClass.R3_EXTERNAL, RiskClass.R4_IRREVERSIBLE):
        return PolicyVerdict(
            Decision.REQUIRE_APPROVAL,
            f"{tool.risk_class} always requires an explicit owner decision.",
        )

    # 9. Quiet hours suppress unattended work, but never turn an approval into
    #    an auto-run — they only ever make the answer more conservative.
    if policy.quiet_hours and now is not None and _in_quiet_hours(now, policy.quiet_hours):
        return PolicyVerdict(
            Decision.REQUIRE_APPROVAL,
            "Inside the owner's quiet hours; unattended work is held.",
            remedy="Approve now, or it will run after quiet hours end.",
        )

    ceiling = AUTO_RUN_CEILING[policy.initiative_level]
    if ceiling is not None and _risk_rank(tool.risk_class) <= _risk_rank(ceiling):
        # An allowlist, when non-empty, is a further narrowing — not a widening.
        if policy.allowed_tools and tool.key not in policy.allowed_tools:
            return PolicyVerdict(
                Decision.REQUIRE_APPROVAL,
                f"{tool.key} is not on the owner's allowed list for unattended use.",
                remedy="Add it to allowed tools to let it run unattended.",
            )
        return PolicyVerdict(Decision.ALLOW, f"{tool.risk_class} is within {policy.initiative_level}.")

    return PolicyVerdict(
        Decision.REQUIRE_APPROVAL,
        f"{tool.risk_class} is above what {policy.initiative_level} runs unattended.",
        remedy="Approve this step, or raise the initiative level for this scope.",
    )


def _in_quiet_hours(now: dt.datetime, window: tuple[int, int]) -> bool:
    """Inclusive of the start hour, exclusive of the end, and wrap-aware so a
    22:00-07:00 window behaves as one night rather than two broken halves."""
    start, end = window
    hour = now.hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end
