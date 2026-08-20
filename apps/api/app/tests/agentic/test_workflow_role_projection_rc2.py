from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.agentic.compiler import ProposedStep, compile_plan
from app.agentic.enums import InitiativeLevel, RiskClass
from app.agentic.policy import OwnerPolicy
from app.brain.schemas import WorkflowProposalV2, WorkflowStepProposal


def _step(*, key: str, role: str, tool_key: str, dependencies: list[str] | None = None) -> WorkflowStepProposal:
    return WorkflowStepProposal(
        key=key,
        title=key,
        description=f"{role} step",
        tool_key=tool_key,
        tool_version="1",
        role=role,
        dependencies=dependencies or [],
    )


def test_brain_workflow_preserves_typed_execution_and_review_roles_in_agency_projection() -> None:
    proposal = WorkflowProposalV2(
        task_id=uuid.uuid4(),
        title="Research then independently verify",
        rationale="The owner must approve both the bounded operation and the read-only review.",
        steps=[
            _step(key="work", role="operator", tool_key="get_plan"),
            _step(key="review", role="security_reviewer", tool_key="get_plan", dependencies=["work"]),
        ],
    )

    assert [step.role for step in proposal.steps] == ["operator", "security_reviewer"]
    assert [step["role"] for step in proposal.to_agency_steps()] == ["operator", "security_reviewer"]
    assert proposal.to_agency_steps()[1]["depends_on"] == ["work"]


@pytest.mark.parametrize("role", ["verifier", "critic", "qa", "security_reviewer", "visual_reviewer"])
def test_workflow_step_proposal_accepts_only_typed_review_roles(role: str) -> None:
    step = _step(key="review", role=role, tool_key="get_plan", dependencies=["work"])
    assert step.role == role


def test_workflow_step_proposal_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        _step(key="review", role="untrusted_executor", tool_key="get_plan", dependencies=["work"])


def _compile_policy(*, permitted: frozenset[str], auto_run: frozenset[str] = frozenset()) -> OwnerPolicy:
    return OwnerPolicy(
        initiative_level=InitiativeLevel.SUGGEST,
        max_risk_class=RiskClass.R1_PRIVATE_DRAFT,
        permitted_tools=permitted,
        auto_run_tools=auto_run,
        granted_capabilities=frozenset({"read_plans"}),
    )


def test_projected_independent_reviewer_reaches_compiler_and_stays_read_only() -> None:
    proposal = WorkflowProposalV2(
        task_id=uuid.uuid4(),
        title="Work then verify",
        rationale="The reviewer must not mutate the owner state.",
        steps=[
            _step(key="work", role="operator", tool_key="get_plan"),
            _step(key="review", role="security_reviewer", tool_key="get_plan", dependencies=["work"]),
        ],
    )
    projected = tuple(
        ProposedStep(
            key=step["key"],
            role=step["role"],
            tool_key=step["tool_key"],
            depends_on=tuple(step["depends_on"]),
            input_refs=dict(step["input_refs"]),
            rationale=step["rationale"],
        )
        for step in proposal.to_agency_steps()
    )

    result = compile_plan(
        projected,
        _compile_policy(permitted=frozenset({"get_plan"}), auto_run=frozenset({"get_plan"})),
    )

    assert result.ok is True
    assert [(step.key, step.role) for step in result.steps] == [
        ("work", "operator"),
        ("review", "security_reviewer"),
    ]
    assert result.approval_keys == ()


def test_projected_verifier_cannot_use_mutating_tool() -> None:
    proposal = WorkflowProposalV2(
        task_id=uuid.uuid4(),
        title="Invalid verifier",
        rationale="A reviewer cannot write the result it reviews.",
        steps=[
            _step(key="work", role="operator", tool_key="get_plan"),
            _step(key="review", role="verifier", tool_key="create_draft_plan", dependencies=["work"]),
        ],
    )
    projected = tuple(
        ProposedStep(
            key=step["key"], role=step["role"], tool_key=step["tool_key"],
            depends_on=tuple(step["depends_on"]), input_refs=dict(step["input_refs"]),
            rationale=step["rationale"],
        )
        for step in proposal.to_agency_steps()
    )

    result = compile_plan(
        projected,
        _compile_policy(permitted=frozenset({"get_plan", "create_draft_plan"})),
    )

    assert result.ok is False
    assert any(error.code == "VERIFIER_MUTATES" and error.step_key == "review" for error in result.errors)
    assert any(error.code == "POLICY_DENIED" and error.step_key == "review" for error in result.errors)
