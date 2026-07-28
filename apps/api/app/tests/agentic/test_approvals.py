"""Exact-call approval.

The guarantee: what executes is the call the owner read, not a call regenerated
afterwards that happens to use the same tool. Every mutation shape is tested,
because "close enough" is how a widened scope gets executed under an old yes.
"""

import datetime as dt

import pytest

from app.agentic.approvals import (
    ApprovalDecision,
    ResumeRefusal,
    StoredApproval,
    apply_edit,
    build_request,
    checkpoint_payload,
    evaluate_resume,
)
from app.agentic.enums import RiskClass
from app.agentic.redaction import REDACTED, contains_secret, redact_arguments, telemetry_safe

NOW = dt.datetime(2026, 7, 29, 12, tzinfo=dt.timezone.utc)


def approved(args, **kw):
    req = build_request(
        tool_key=kw.pop("tool_key", "schedule_timeline_event"),
        tool_version=kw.pop("tool_version", "1"),
        arguments=args,
        rationale="because the scope review keeps moving",
        risk_class=RiskClass.R2_DURABLE_PRIVATE,
        reversible=True,
        scope_summary="Ambition system",
        **kw,
    )
    return StoredApproval(
        tool_key=req.tool_key,
        tool_version=req.tool_version,
        argument_digest=req.digest,
        redacted_arguments=req.redacted_arguments,
        decision=ApprovalDecision.APPROVED,
        cost_ceiling_cents=req.cost_ceiling_cents,
        expires_at=req.expires_at,
    )


def test_the_approved_call_resumes():
    args = {"title": "Scope review", "when": "2026-08-04"}
    verdict = evaluate_resume(approved(args), tool_key="schedule_timeline_event",
                              tool_version="1", arguments=args, now=NOW)
    assert verdict.allowed
    assert verdict.arguments == args


def test_a_changed_argument_invalidates_the_approval():
    stored = approved({"title": "Scope review", "when": "2026-08-04"})
    verdict = evaluate_resume(stored, tool_key="schedule_timeline_event", tool_version="1",
                              arguments={"title": "Scope review", "when": "2026-08-11"}, now=NOW)
    assert not verdict.allowed
    assert verdict.refusal is ResumeRefusal.ARGUMENTS_CHANGED
    assert verdict.arguments is None


def test_a_widened_argument_set_invalidates_the_approval():
    """Adding a field is the scope-widening case and must not slip through."""
    stored = approved({"recipient": "a@example.com"})
    verdict = evaluate_resume(stored, tool_key="schedule_timeline_event", tool_version="1",
                              arguments={"recipient": "a@example.com", "include_journal": True},
                              now=NOW)
    assert verdict.refusal is ResumeRefusal.ARGUMENTS_CHANGED


def test_a_removed_argument_also_invalidates():
    stored = approved({"title": "x", "when": "y"})
    verdict = evaluate_resume(stored, tool_key="schedule_timeline_event", tool_version="1",
                              arguments={"title": "x"}, now=NOW)
    assert verdict.refusal is ResumeRefusal.ARGUMENTS_CHANGED


def test_key_reordering_does_not_invalidate():
    """An approval must survive a dict being rebuilt."""
    stored = approved({"title": "x", "when": "y"})
    verdict = evaluate_resume(stored, tool_key="schedule_timeline_event", tool_version="1",
                              arguments={"when": "y", "title": "x"}, now=NOW)
    assert verdict.allowed


def test_a_different_tool_is_refused_specifically():
    stored = approved({"a": 1})
    verdict = evaluate_resume(stored, tool_key="create_capsule", tool_version="1",
                              arguments={"a": 1}, now=NOW)
    assert verdict.refusal is ResumeRefusal.TOOL_CHANGED


def test_a_tool_version_change_is_refused():
    """Same arguments, different behaviour — the old decision no longer describes
    what would happen."""
    stored = approved({"a": 1})
    verdict = evaluate_resume(stored, tool_key="schedule_timeline_event", tool_version="2",
                              arguments={"a": 1}, now=NOW)
    assert verdict.refusal is ResumeRefusal.VERSION_CHANGED


def test_an_expired_approval_cannot_be_redeemed():
    stored = approved({"a": 1}, expires_at=NOW - dt.timedelta(minutes=1))
    verdict = evaluate_resume(stored, tool_key="schedule_timeline_event", tool_version="1",
                              arguments={"a": 1}, now=NOW)
    assert verdict.refusal is ResumeRefusal.EXPIRED


@pytest.mark.parametrize(
    "decision",
    [ApprovalDecision.PENDING, ApprovalDecision.REJECTED,
     ApprovalDecision.EXPIRED, ApprovalDecision.INVALIDATED],
)
def test_only_approved_or_edited_may_resume(decision):
    stored = StoredApproval("t", "1", "sha256:x", {}, decision)
    verdict = evaluate_resume(stored, tool_key="t", tool_version="1", arguments={}, now=NOW)
    assert verdict.refusal is ResumeRefusal.NOT_APPROVED


def test_cost_above_the_approved_ceiling_is_refused():
    stored = approved({"a": 1}, cost_ceiling_cents=50)
    verdict = evaluate_resume(stored, tool_key="schedule_timeline_event", tool_version="1",
                              arguments={"a": 1}, now=NOW, estimated_cost_cents=51)
    assert verdict.refusal is ResumeRefusal.COST_CEILING_EXCEEDED


def test_an_unredacted_checkpoint_cannot_be_replayed():
    stored = approved({"a": 1})
    verdict = evaluate_resume(stored, tool_key="schedule_timeline_event", tool_version="1",
                              arguments={"a": 1}, now=NOW, checkpoint_redacted=False)
    assert verdict.refusal is ResumeRefusal.CHECKPOINT_UNREDACTED


def test_an_edit_rebinds_rather_than_reusing_the_old_digest():
    """Editing is approving something different; keeping the old digest would let
    an edit widen a call without a fresh decision."""
    stored = approved({"when": "2026-08-04"})
    edited = apply_edit(stored, {"when": "2026-08-11"})
    assert edited.argument_digest != stored.argument_digest
    assert edited.decision is ApprovalDecision.EDITED
    # The edited call resumes; the original one no longer does.
    assert evaluate_resume(edited, tool_key=stored.tool_key, tool_version="1",
                           arguments={"when": "2026-08-11"}, now=NOW).allowed
    assert not evaluate_resume(edited, tool_key=stored.tool_key, tool_version="1",
                               arguments={"when": "2026-08-04"}, now=NOW).allowed


# ── redaction ────────────────────────────────────────────────────────────────

def test_secrets_are_masked_but_the_key_survives():
    """A dropped key would make the approval card quietly incomplete."""
    out = redact_arguments({"api_key": "sk-live-123", "title": "Review"})
    assert out["api_key"] == REDACTED
    assert "api_key" in out
    assert out["title"] == "Review"


def test_secrets_are_masked_at_any_depth():
    out = redact_arguments({"outer": {"list": [{"authorization": "Bearer x"}]}})
    assert out["outer"]["list"][0]["authorization"] == REDACTED


def test_owner_prose_reaches_the_card_but_not_telemetry():
    args = {"journal_text": "I have been avoiding this", "title": "Review"}
    assert redact_arguments(args)["journal_text"] == "I have been avoiding this"
    assert telemetry_safe(args)["journal_text"] == REDACTED


def test_telemetry_strips_email_addresses_from_free_text():
    assert "@" not in telemetry_safe({"note": "ping mahnoor@example.com today"})["note"]


def test_contains_secret_detects_an_unmasked_token():
    assert contains_secret({"session_token": "abc"})
    assert not contains_secret(redact_arguments({"session_token": "abc"}))


def test_checkpoint_payload_refuses_to_mark_a_leaky_blob_safe():
    cleaned, safe = checkpoint_payload({"password": "hunter2", "step": 3})
    assert cleaned["password"] == REDACTED
    assert safe is True
    assert cleaned["step"] == 3
