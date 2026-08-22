from uuid import uuid4

import pytest

from app.brain.critic import IndependentCritic
from app.brain.planner import BoundedSimulator, PlanBudget, TypedPlanner
from app.brain.evaluation import EvaluationCase, EvaluationGate
from app.brain.research import ResearchBrain, ResearchSource
from app.brain.schemas import (
    BrainProfileKey,
    CognitiveResultV2,
    CognitiveTaskPacket,
    CognitiveTaskPacketV2,
    ContextManifest,
    ContextSource,
    IdentitySnapshot,
    SelfCapabilities,
    WorkflowProposal,
    WorkflowProposalV2,
    WorkflowStepProposal,
)
from app.brain.specialists import SpecialistBudget, SpecialistWorker


def packet() -> CognitiveTaskPacket:
    return CognitiveTaskPacket(
        owner_user_id=uuid4(),
        task_class="research",
        user_input="Compare the supplied claims.",
        identity=IdentitySnapshot(version="v1", name="NUR"),
        self_capabilities=SelfCapabilities(provider_name="test", provider_available=False),
        context_manifest=ContextManifest(
            scope_statement="private owner scope",
            included=[ContextSource(kind="DECISION", id="d1", reason="owner source")],
            excluded=[ContextSource(kind="SECRET", id="s1", reason="excluded by policy")],
            token_budget=100,
            token_used=20,
        ),
    )


def test_context_packet_enumerates_target_context_families_and_manifest_lineage() -> None:
    current = packet()
    families = {
        "identity": current.identity,
        "self": current.self_capabilities,
        "world": current.context_manifest,
        "evidence": current.evidence_refs,
        "beliefs": current.active_beliefs,
        "hypotheses": current.active_hypotheses,
    }
    assert set(families) == {"identity", "self", "world", "evidence", "beliefs", "hypotheses"}
    assert current.context_manifest.included[0].id == "d1"
    assert current.context_manifest.excluded[0].kind == "SECRET"
    assert current.context_manifest.token_used <= current.context_manifest.token_budget


def test_v2_contracts_preserve_visible_fields_and_add_versions() -> None:
    current = packet()
    upgraded = CognitiveTaskPacketV2.from_v1(current)
    assert upgraded.contract_version == "cognitive-task-v2"
    assert upgraded.user_input == current.user_input
    result = CognitiveResultV2.from_v1(
        task_id=current.task_id,
        result={
            "profile_used": BrainProfileKey.BALANCED,
            "direct_response": "Grounded.",
        },
    )
    assert result.contract_version == "cognitive-result-v2"
    assert result.direct_response == "Grounded."


def test_typed_planner_and_bounded_simulator_are_separate_roles() -> None:
    current = packet()
    proposal = TypedPlanner().plan(
        current,
        tool_key="get_timeline",
        arguments={"limit": 3},
        budget=PlanBudget(max_steps=2, max_cost_cents=10),
    )
    simulation = BoundedSimulator().simulate(proposal, budget=PlanBudget(max_steps=2, max_cost_cents=10))
    assert proposal.contract_version == "workflow-proposal-v2"
    assert simulation.allowed is True
    assert simulation.comparisons == ["steps=1", "cost=0"]
    costly = proposal.model_copy(update={
        "steps": [proposal.steps[0].model_copy(update={"estimated_cost_cents": 1})],
    })
    blocked = BoundedSimulator().simulate(costly, budget=PlanBudget(max_steps=1, max_cost_cents=0))
    assert blocked.allowed is False


def test_independent_critic_is_distinct_from_deterministic_validator() -> None:
    current = packet()
    result = CognitiveResultV2(
        task_id=current.task_id,
        profile_used=BrainProfileKey.BALANCED,
        direct_response="A claim.",
        claims=[{"claim_text": "Unsupported", "claim_kind": "inferred", "source_refs": []}],
    )
    critique = IndependentCritic().critique(current, result)
    assert critique.role == "independent_critic"
    assert critique.verdict == "REVISE"
    assert critique.notes


def test_research_brain_validates_citations_and_contradictions() -> None:
    sources = [
        ResearchSource(id="a", title="A", text="The sky is blue.", citation="https://a.test"),
        ResearchSource(id="b", title="B", text="The sky is not blue.", citation="https://b.test"),
    ]
    report = ResearchBrain(allowed_domains={"a.test", "b.test"}).analyze(
        "Is the sky blue?", sources
    )
    assert report.contradictions
    assert report.citations_valid is True
    assert set(report.source_ids) == {"a", "b"}


def test_specialist_worker_is_bounded_and_scoped() -> None:
    worker = SpecialistWorker("research", allowed_capabilities={"retrieve"})
    result = worker.run("retrieve", {"query": "q"}, SpecialistBudget(max_calls=1, max_tokens=20))
    assert result.completed is True
    with pytest.raises(PermissionError):
        worker.run("write", {}, SpecialistBudget(max_calls=1, max_tokens=20))


def test_workflow_proposal_v2_has_one_canonical_agency_projection() -> None:
    proposal = WorkflowProposal(
        task_id=uuid4(),
        title="Draft",
        rationale="Owner requested it.",
        steps=[WorkflowStepProposal(title="Read", description="Read", tool_key="get_timeline", tool_version="1")],
    )
    upgraded = WorkflowProposalV2.from_v1(proposal)
    assert upgraded.contract_version == "workflow-proposal-v2"
    assert upgraded.to_agency_steps()[0]["tool_key"] == "get_timeline"


def test_evaluation_gate_requires_held_out_and_shadow_before_promotion() -> None:
    gate = EvaluationGate(
        cases=[
            EvaluationCase(case_id="one", split="held_out", expected="pass"),
            EvaluationCase(case_id="shadow", split="shadow", expected="pass"),
        ],
        shadow_pass_rate=1.0,
    )
    assert gate.can_promote({"one": "pass"}) is False
    assert gate.can_promote({"one": "pass", "shadow": "pass"}) is True
    blocked = EvaluationGate(
        cases=[
            EvaluationCase(case_id="one", split="held_out", expected="pass"),
            EvaluationCase(case_id="shadow", split="shadow", expected="pass"),
        ],
        shadow_pass_rate=1.0,
    )
    assert blocked.can_promote({"one": "pass", "shadow": "fail"}) is False
