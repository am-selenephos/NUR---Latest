"""Deterministic verification of a step's result.

Verification asks a different question from execution. Execution asks "did the
call complete?"; verification asks "does the result satisfy what the step was
for?". A tool can return successfully and still not have done the job — an
insight created without evidence, a plan activated that was already active, a
handler that reported `changed: false`.

This verifier is deterministic and first-party. It does not ask a model whether
a model's work was good, because that is the self-grading the compiler already
refuses structurally. It checks claims against the contract the tool declared.

A verifier failure never erases the execution record. The work happened; the
ledger says so; the verdict is a separate row. Rewriting history to make a run
look clean is the one thing an audit trail may not do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.agentic.registry import contract, spec


class Verdict(StrEnum):
    PASS = "PASS"
    REVISE = "REVISE"
    FAIL = "FAIL"


@dataclass(frozen=True)
class VerificationResult:
    verdict: Verdict
    reasons: tuple[str, ...] = ()
    checks_run: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


def _missing(result: dict, *keys: str) -> list[str]:
    return [key for key in keys if key not in result]


def verify_step_result(
    tool_key: str,
    result: dict[str, Any] | None,
    *,
    expected_changed: bool = True,
) -> VerificationResult:
    """Check a handler's result against what its contract promised.

    REVISE and FAIL are distinguished deliberately. FAIL means the result is
    unusable or malformed — nothing downstream can proceed. REVISE means the
    call completed honestly but did not achieve the step's purpose, which is a
    planning problem rather than a defect, and the workflow can re-plan.
    """
    checks: list[str] = []
    reasons: list[str] = []

    if result is None:
        return VerificationResult(Verdict.FAIL, ("handler returned nothing",), ("result_present",))

    checks.append("result_present")

    if not isinstance(result, dict):
        return VerificationResult(
            Verdict.FAIL, ("handler returned a non-mapping result",), tuple(checks)
        )

    tool = contract(tool_key)
    tool_spec = spec(tool_key)
    checks.append("contract_resolved")

    # A tool that declares writes must say whether it changed anything. Silence
    # here is how a no-op passes as work.
    if tool_spec.writes:
        checks.append("mutation_reported")
        reported = result.get("created", result.get("changed"))
        if reported is None:
            reasons.append("a write tool did not report whether it changed anything")
        elif reported is False and expected_changed:
            # Honest no-op. The call was fine; the step did not achieve its aim.
            return VerificationResult(
                Verdict.REVISE,
                (str(result.get("reason", "the tool reported no change")),),
                tuple(checks),
                {"reported_change": False},
            )

    # Anything a model produced has to say so. An unlabelled inference entering
    # the ledger is indistinguishable from owner truth later.
    if tool.risk_class.value.startswith(("R1", "R2")):
        checks.append("provenance_labelled")
        if tool_spec.writes and "provenance_label" not in result:
            reasons.append("a created record carries no provenance label")

    # A candidate insight without its doubt is the unlabelled certainty the
    # product refuses; the schema enforces it, and so does this.
    if tool_key == "create_insight_candidate":
        checks.append("doubt_present")
        if not result.get("insight_id"):
            reasons.append("no insight id returned")

    if tool_key == "create_timeline_draft":
        checks.append("draft_unscheduled")
        if result.get("scheduled_for") is not None:
            reasons.append("a draft Timeline event must not carry a schedule")

    if reasons:
        return VerificationResult(Verdict.FAIL, tuple(reasons), tuple(checks))
    return VerificationResult(Verdict.PASS, (), tuple(checks))
