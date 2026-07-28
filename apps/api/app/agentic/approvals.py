"""Exact-call approval: pause, hold, and resume the thing the owner agreed to.

The guarantee this module exists to provide is narrow and absolute: what
executes after an approval is the call the owner read, not a call regenerated
afterwards that happens to use the same tool.

That distinction is the whole attack surface. A model asked to "schedule the
review" produces arguments; the owner approves those arguments; if execution
then re-asks the model rather than replaying the stored call, a second
generation can differ from the first in ways nobody reviewed — a different date,
a widened recipient list, an extra include flag. The approval would still look
satisfied. So resume never regenerates: it replays `redacted_arguments` and
verifies the digest still matches before doing so.

Everything here is pure. The database writes live in the service layer; these
are the decisions, so they can be tested against every mutation shape rather
than through a fixture.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from app.agentic.enums import ApprovalDecision, RiskClass
from app.agentic.orchestrator import argument_digest
from app.agentic.redaction import contains_secret, redact_arguments


class ResumeRefusal(StrEnum):
    NOT_APPROVED = "NOT_APPROVED"
    ARGUMENTS_CHANGED = "ARGUMENTS_CHANGED"
    EXPIRED = "EXPIRED"
    TOOL_CHANGED = "TOOL_CHANGED"
    VERSION_CHANGED = "VERSION_CHANGED"
    COST_CEILING_EXCEEDED = "COST_CEILING_EXCEEDED"
    CHECKPOINT_UNREDACTED = "CHECKPOINT_UNREDACTED"


@dataclass(frozen=True)
class ApprovalRequest:
    """What the owner is shown. Every field here appears on the card."""

    tool_key: str
    tool_version: str
    arguments: dict
    rationale: str
    risk_class: RiskClass
    reversible: bool
    scope_summary: str
    expected_result: str | None = None
    cost_ceiling_cents: int = 0
    expires_at: dt.datetime | None = None

    @property
    def redacted_arguments(self) -> dict:
        # Secrets masked, but owner prose kept: the owner is entitled to read
        # the text NUR proposes to act on, since that is what they are approving.
        return redact_arguments(self.arguments)

    @property
    def digest(self) -> str:
        return argument_digest(self.tool_key, self.tool_version, self.arguments)


@dataclass(frozen=True)
class StoredApproval:
    """The persisted decision, as `agent_approvals` holds it."""

    tool_key: str
    tool_version: str
    argument_digest: str
    redacted_arguments: dict
    decision: ApprovalDecision
    cost_ceiling_cents: int = 0
    expires_at: dt.datetime | None = None
    edited_arguments: dict | None = None


@dataclass(frozen=True)
class ResumeVerdict:
    allowed: bool
    refusal: ResumeRefusal | None = None
    message: str = ""
    # The arguments that may actually execute. Populated only on success, so a
    # caller cannot accidentally use a rejected call's payload.
    arguments: dict | None = None


def build_request(
    *,
    tool_key: str,
    tool_version: str,
    arguments: dict,
    rationale: str,
    risk_class: RiskClass,
    reversible: bool,
    scope_summary: str,
    expected_result: str | None = None,
    cost_ceiling_cents: int = 0,
    expires_at: dt.datetime | None = None,
) -> ApprovalRequest:
    return ApprovalRequest(
        tool_key=tool_key,
        tool_version=tool_version,
        arguments=dict(arguments),
        rationale=rationale,
        risk_class=risk_class,
        reversible=reversible,
        scope_summary=scope_summary,
        expected_result=expected_result,
        cost_ceiling_cents=cost_ceiling_cents,
        expires_at=expires_at,
    )


def apply_edit(stored: StoredApproval, edited: dict) -> StoredApproval:
    """An owner edit produces a new binding, not a mutation of the old one.

    Editing is genuinely approving something different, so the digest is
    recomputed from the edited arguments. The alternative — keeping the original
    digest — would let an edit widen a call without a fresh decision.
    """
    return StoredApproval(
        tool_key=stored.tool_key,
        tool_version=stored.tool_version,
        argument_digest=argument_digest(stored.tool_key, stored.tool_version, edited),
        redacted_arguments=redact_arguments(edited),
        decision=ApprovalDecision.EDITED,
        cost_ceiling_cents=stored.cost_ceiling_cents,
        expires_at=stored.expires_at,
        edited_arguments=dict(edited),
    )


def evaluate_resume(
    stored: StoredApproval,
    *,
    tool_key: str,
    tool_version: str,
    arguments: dict,
    now: dt.datetime,
    estimated_cost_cents: int = 0,
    checkpoint_redacted: bool = True,
) -> ResumeVerdict:
    """Decide whether the call about to run is the call that was approved.

    Order is chosen so the refusal names the most specific difference. Reporting
    "arguments changed" when the tool itself changed would send someone
    diffing a payload that was never the problem.
    """
    if stored.decision not in (ApprovalDecision.APPROVED, ApprovalDecision.EDITED):
        return ResumeVerdict(
            False, ResumeRefusal.NOT_APPROVED,
            f"approval is {stored.decision}, not an approval",
        )

    if stored.expires_at is not None and now >= stored.expires_at:
        return ResumeVerdict(
            False, ResumeRefusal.EXPIRED,
            "the approval expired; ask again rather than assuming consent persists",
        )

    if tool_key != stored.tool_key:
        return ResumeVerdict(
            False, ResumeRefusal.TOOL_CHANGED,
            f"approved {stored.tool_key!r}, about to run {tool_key!r}",
        )

    if tool_version != stored.tool_version:
        # A tool version change may alter behaviour with identical arguments,
        # so the earlier decision no longer describes what would happen.
        return ResumeVerdict(
            False, ResumeRefusal.VERSION_CHANGED,
            f"approved {stored.tool_key} v{stored.tool_version}, about to run v{tool_version}",
        )

    if argument_digest(tool_key, tool_version, arguments) != stored.argument_digest:
        return ResumeVerdict(
            False, ResumeRefusal.ARGUMENTS_CHANGED,
            "the arguments differ from the ones approved; a new decision is required",
        )

    if stored.cost_ceiling_cents and estimated_cost_cents > stored.cost_ceiling_cents:
        return ResumeVerdict(
            False, ResumeRefusal.COST_CEILING_EXCEEDED,
            f"{estimated_cost_cents}c exceeds the approved ceiling of {stored.cost_ceiling_cents}c",
        )

    if not checkpoint_redacted:
        return ResumeVerdict(
            False, ResumeRefusal.CHECKPOINT_UNREDACTED,
            "the checkpoint was never redacted and must not be replayed",
        )

    return ResumeVerdict(True, None, "resuming the approved call", arguments=dict(arguments))


def checkpoint_payload(state: dict) -> tuple[dict, bool]:
    """Prepare agent run state for `agent_checkpoints`.

    Returns the redacted blob and whether it is safe to persist. The caller sets
    `redacted` from the second value; `evaluate_resume` refuses to replay a
    checkpoint whose flag is false, so an unredacted blob cannot be resumed even
    if something managed to write it.
    """
    cleaned = redact_arguments(state)
    return cleaned, not contains_secret(cleaned)
