"""The execution loop's ordering, which is its whole design.

Two orderings are non-negotiable and neither can be verified by reading a call
site: the gate must sit between the claim and the handler, and the result must
be recorded before verification.
"""

import inspect

from app.agentic import runtime


def _order(source: str, *needles: str) -> list[int]:
    return [source.index(n) for n in needles]


def test_policy_is_evaluated_after_the_claim_and_before_the_handler():
    """Before the claim, two workers would both pass the gate. After the
    handler, it is not a gate."""
    source = inspect.getsource(runtime.execute_step)
    claim, gate, handler = _order(source, "claim_step(", "evaluate(contract", "registry.handler(")
    assert claim < gate < handler


def test_approval_is_checked_before_the_handler_resolves():
    source = inspect.getsource(runtime.execute_step)
    approval, handler = _order(source, "REQUIRE_APPROVAL", "registry.handler(")
    assert approval < handler


def test_the_result_is_recorded_before_verification():
    """A step that crashed during verification must not look like one that never
    ran. Work that happened has to appear in the ledger regardless."""
    source = inspect.getsource(runtime.execute_step)
    record = source.rindex("_record_tool_call(")
    verify = source.rindex("StepState.VERIFYING")
    assert record < verify


def test_a_denied_call_is_still_recorded():
    """A denial is the evidence the gate did its job. A trail holding only
    successful calls cannot demonstrate anything was ever prevented."""
    source = inspect.getsource(runtime.execute_step)
    assert '"DENIED"' in source
    assert "denial_reason=verdict.reason" in source


def test_a_failed_call_is_recorded_too():
    source = inspect.getsource(runtime.execute_step)
    assert '"FAILED"' in source


def test_exception_messages_never_reach_the_ledger():
    """A message can carry the owner text the tool was handling."""
    source = inspect.getsource(runtime.execute_step)
    assert "type(error).__name__" in source
    assert "str(error)" not in source
    assert "{error}" not in source


def test_awaiting_approval_is_an_outcome_not_a_failure():
    source = inspect.getsource(runtime.execute_step)
    assert "STEP_AWAITING_APPROVAL" in source
    assert "StepState.WAITING_APPROVAL" in source


def test_a_lost_claim_returns_rather_than_raising():
    """A duplicate delivery is normal operation; raising would make ordinary
    behaviour look like failure in the logs."""
    source = inspect.getsource(runtime.execute_step)
    lost = source.index("if not claim.claimed")
    assert "return StepOutcome" in source[lost:lost + 300]


def test_a_step_that_cannot_be_reread_raises_rather_than_continuing():
    """Claiming a row we then cannot read means the RLS context is wrong, which
    is a fault, not a state."""
    source = inspect.getsource(runtime.execute_step)
    assert "RuntimeRefusal" in source
    assert "RLS context is wrong" in source


def test_tool_call_arguments_are_redacted_before_persisting():
    assert "redact_arguments(arguments)" in inspect.getsource(runtime._record_tool_call)


def test_no_provider_call_exists_in_the_loop():
    """Adding a model call without guardrails, budget accounting and
    checkpointing would make the layer look finished while being unsafe."""
    source = inspect.getsource(runtime)
    for needle in ("openai", "OpenAI", "chat.completions", "Runner.run", "responses.create"):
        assert needle not in source


def test_the_loop_never_transitions_running_straight_to_succeeded():
    """Verification is structural; the state machine forbids the shortcut and the
    runtime must not attempt it."""
    source = inspect.getsource(runtime.execute_step)
    assert "nxt=StepState.SUCCEEDED" not in source
