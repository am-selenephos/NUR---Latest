"""The edited-approval path, which was previously unreachable.

`evaluate_resume` was called with the original step arguments while an EDITED
approval carries a digest recomputed from the edit. The two could never match,
so the branch applying `edited_arguments` was dead code and an owner's edit was
silently ignored — the call would simply refuse and park.

These test the selection logic directly rather than through the runtime, so the
property holds regardless of how the runtime is later restructured.
"""

import datetime as dt

import pytest

from app.agentic.approvals import StoredApproval, apply_edit, evaluate_resume
from app.agentic.enums import ApprovalDecision
from app.agentic.orchestrator import argument_digest

NOW = dt.datetime(2026, 7, 29, 12, tzinfo=dt.timezone.utc)
TOOL, VERSION = "schedule_timeline_event", "1"
ORIGINAL = {"event_id": "e1", "scheduled_for": "2026-08-04"}
EDITED = {"event_id": "e1", "scheduled_for": "2026-08-11"}


def approved(arguments):
    return StoredApproval(
        tool_key=TOOL, tool_version=VERSION,
        argument_digest=argument_digest(TOOL, VERSION, arguments),
        redacted_arguments=arguments, decision=ApprovalDecision.APPROVED,
    )


def effective_arguments(approval: StoredApproval, step_arguments: dict) -> dict:
    """The selection the runtime makes before validating."""
    if approval.decision is ApprovalDecision.EDITED and approval.edited_arguments:
        return dict(approval.edited_arguments)
    return dict(step_arguments)


def test_approved_executes_the_original_payload():
    approval = approved(ORIGINAL)
    payload = effective_arguments(approval, ORIGINAL)
    verdict = evaluate_resume(
        approval, tool_key=TOOL, tool_version=VERSION, arguments=payload, now=NOW
    )
    assert verdict.allowed
    assert verdict.arguments == ORIGINAL


def test_edited_executes_the_edited_payload():
    edited = apply_edit(approved(ORIGINAL), EDITED)
    payload = effective_arguments(edited, ORIGINAL)
    assert payload == EDITED
    verdict = evaluate_resume(
        edited, tool_key=TOOL, tool_version=VERSION, arguments=payload, now=NOW
    )
    assert verdict.allowed, "the edited path must be reachable"
    assert verdict.arguments == EDITED


def test_the_original_payload_never_executes_after_an_edit():
    edited = apply_edit(approved(ORIGINAL), EDITED)
    verdict = evaluate_resume(
        edited, tool_key=TOOL, tool_version=VERSION, arguments=ORIGINAL, now=NOW
    )
    assert not verdict.allowed
    assert verdict.arguments is None


def test_the_edited_digest_is_recomputed_and_matched():
    edited = apply_edit(approved(ORIGINAL), EDITED)
    assert edited.argument_digest == argument_digest(TOOL, VERSION, EDITED)
    assert edited.argument_digest != argument_digest(TOOL, VERSION, ORIGINAL)


def test_the_payload_that_passes_the_gate_is_what_is_returned():
    """The handler and the ledger must both receive exactly what was validated;
    anything else means auditing a call that did not run."""
    edited = apply_edit(approved(ORIGINAL), EDITED)
    payload = effective_arguments(edited, ORIGINAL)
    verdict = evaluate_resume(
        edited, tool_key=TOOL, tool_version=VERSION, arguments=payload, now=NOW
    )
    assert verdict.arguments == payload


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("tool_key", "create_capsule", "TOOL_CHANGED"),
        ("tool_version", "2", "VERSION_CHANGED"),
    ],
)
def test_an_edit_does_not_relax_the_other_checks(field, value, expected):
    edited = apply_edit(approved(ORIGINAL), EDITED)
    kwargs = {"tool_key": TOOL, "tool_version": VERSION, "arguments": EDITED, "now": NOW}
    kwargs[field] = value
    verdict = evaluate_resume(edited, **kwargs)
    assert verdict.refusal.value == expected


def test_an_edited_but_expired_approval_still_refuses():
    edited = apply_edit(approved(ORIGINAL), EDITED)
    expired = StoredApproval(
        tool_key=edited.tool_key, tool_version=edited.tool_version,
        argument_digest=edited.argument_digest,
        redacted_arguments=edited.redacted_arguments,
        decision=ApprovalDecision.EDITED,
        expires_at=NOW - dt.timedelta(minutes=1),
        edited_arguments=EDITED,
    )
    verdict = evaluate_resume(
        expired, tool_key=TOOL, tool_version=VERSION, arguments=EDITED, now=NOW
    )
    assert verdict.refusal.value == "EXPIRED"


def test_the_runtime_selects_the_payload_before_validating():
    """Guards the ordering that made the path dead: selection must precede the
    evaluate_resume call, not follow it."""
    import ast
    import inspect

    from app.agentic import runtime

    code = ast.unparse(ast.parse(inspect.getsource(runtime.execute_step).lstrip()))
    select = code.index("effective_arguments")
    validate = code.index("evaluate_resume(")
    assert select < validate
