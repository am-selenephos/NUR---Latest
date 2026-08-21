from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import AsyncMock

import pytest

from app.agentic.dispatcher import (
    DispatchIntent,
    dispatch_once,
    validate_dispatch_snapshot,
)
from app.agentic.limits import DAGExecutionLimits
from app.brain.cognition import run_brain_step
from app.brain.evaluation import (
    EvaluationCase,
    EvaluationCorpus,
    EvaluationGate,
    EvaluationRunner,
)
from app.brain.schemas import (
    BrainProfileKey,
    CognitiveBudget,
    CognitiveClaim,
    CognitiveResult,
    CognitiveTaskPacketV2,
    ContextManifest,
    IdentitySnapshot,
    ScopeEnvelope,
    SelfCapabilities,
    WorkflowProposal,
    WorkflowStepProposal,
)
from app.mind.agency_bridge import submit_workflow_proposal
from app.mind.capabilities.hydrator import ContextHydrator, HydratedCapabilityContext
from app.mind.capabilities.dispatcher import WorkerDispatcher
from app.mind.capabilities.definitions.plan_from_conversation import PLAN_FROM_CONVERSATION_SPEC
from app.mind.context import build_cognitive_task_packet


def _identity() -> IdentitySnapshot:
    return IdentitySnapshot(version="test-v1", name="NUR")


def _capabilities() -> SelfCapabilities:
    return SelfCapabilities(
        provider_name="test",
        provider_available=True,
        model="test-model",
        daily_budget_remaining=100,
    )


@pytest.mark.asyncio
async def test_production_builder_returns_rich_v2_with_owner_intent_and_lineage(monkeypatch) -> None:
    owner_id = uuid.uuid4()
    other_owner = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="plan",
        orbit_id=uuid.uuid4(),
        reason="private owner plan scope",
    )
    manifest = ContextManifest(scope_statement="private owner plan scope", token_budget=200, token_used=20)
    hydrated = HydratedCapabilityContext(
        capability_id="capability:plan_from_conversation",
        scope_envelope=scope,
        manifest=manifest,
        approved_memory=[
            {
                "id": "memory-owner",
                "owner_user_id": str(owner_id),
                "content": "The owner prefers reversible plans.",
                "status": "APPROVED",
            },
            {
                "id": "memory-other",
                "owner_user_id": str(other_owner),
                "content": "Must never cross the boundary.",
                "status": "APPROVED",
            },
        ],
        beliefs=[
            {
                "id": "belief-owner",
                "owner_user_id": str(owner_id),
                "claim": "The deadline is Friday.",
                "confidence": 0.7,
                "supporting_evidence": [{"id": "support-1", "rationale": "Owner calendar"}],
                "counterevidence": [{"id": "counter-1", "rationale": "Date may move"}],
            },
            {
                "id": "belief-other",
                "owner_user_id": str(other_owner),
                "claim": "Cross-owner secret.",
            },
        ],
        user_model_claims=[
            {
                "id": "user-model-owner",
                "owner_user_id": str(owner_id),
                "claim": "Owner wants a short plan.",
                "claim_class": "owner_stated",
            }
        ],
        active_plans=[{"id": "plan-1", "title": "Inferred older plan"}],
        orbit_context={"id": str(scope.orbit_id), "title": "Launch orbit"},
        source_statuses={"active_plans": "INCLUDED", "timeline": "DEGRADED"},
        estimated_tokens=20,
    )
    monkeypatch.setattr("app.mind.context.load_identity", _identity)
    monkeypatch.setattr(
        "app.mind.context.get_self_capabilities",
        AsyncMock(return_value=_capabilities()),
    )

    packet = await build_cognitive_task_packet(
        AsyncMock(),
        owner_user_id=owner_id,
        user_input="Make me a reversible launch plan for next week.",
        task_class="plan",
        orbit_id=scope.orbit_id,
        scope_envelope=scope,
        hydrated_context=hydrated,
        token_budget=200,
    )

    assert isinstance(packet, CognitiveTaskPacketV2)
    assert packet.owner_user_id == owner_id
    assert packet.intention.explicit_owner_intent == "Make me a reversible launch plan for next week."
    assert packet.intention.effective_intent == packet.intention.explicit_owner_intent
    assert packet.intention.precedence == "explicit_owner_intent"
    assert packet.context_lineage.scope_envelope_id == scope.scope_id
    assert packet.context_lineage.capability_id == hydrated.capability_id
    assert packet.world_model.orbit["id"] == str(scope.orbit_id)
    assert packet.user_model.claims[0]["id"] == "user-model-owner"
    assert packet.beliefs[0].counterevidence[0]["id"] == "counter-1"
    assert {item["id"] for item in packet.approved_memory} == {"memory-owner"}
    assert all("Cross-owner" not in belief.claim for belief in packet.beliefs)
    assert any(source.id == "memory-other" for source in packet.context_manifest.excluded)
    assert packet.budget.max_context_tokens == packet.context_manifest.token_budget
    assert packet.context_manifest.token_used <= packet.budget.max_context_tokens


def test_semantic_hydration_records_budget_degradation_in_manifest() -> None:
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(owner_user_id=owner_id, reason="private owner scope")
    result = ContextHydrator.hydrate_semantic_sources(
        scope,
        approved_memory=[
            {
                "id": "too-large",
                "owner_user_id": str(owner_id),
                "status": "APPROVED",
                "content": "x" * 100,
            }
        ],
        memory_candidates=[],
        beliefs=[],
        user_model_claims=[],
        research_results=[],
        semantic_context=[],
        token_budget=1,
    )

    source = next(item for item in result.manifest.excluded if item.id == "too-large")
    assert source.status == "TRUNCATED"
    assert source.truncated is True
    assert source.degraded is True
    assert result.manifest.degraded[0].id == "too-large"
    assert result.manifest.token_used <= result.manifest.token_budget


@pytest.mark.asyncio
async def test_brain_routes_semantic_roles_without_tool_side_effects(monkeypatch) -> None:
    packet = CognitiveTaskPacketV2(
        owner_user_id=uuid.uuid4(),
        task_class="research",
        user_input="Research and challenge this high-stakes financial plan.",
        identity=_identity(),
        self_capabilities=_capabilities(),
        context_manifest=ContextManifest(scope_statement="private", token_budget=500, token_used=30),
        evidence_refs=[
            {
                "kind": "research",
                "id": "source-1",
                "excerpt": "The plan assumes revenue with no observed proof.",
                "citation": "https://evidence.nur.test/source-1",
            }
        ],
        risk_flags=["financial", "high_stakes"],
        budget=CognitiveBudget(
            max_context_tokens=500,
            max_model_calls=1,
            max_cost_cents=100,
            deadline_seconds=30,
        ),
    )
    provider_result = CognitiveResult(
        task_id=packet.task_id,
        profile_used=BrainProfileKey.DEEP,
        direct_response="The plan needs evidence.",
        claims=[
            CognitiveClaim(
                claim_text="Revenue is guaranteed.",
                claim_kind="inferred",
                source_refs=[],
            )
        ],
    )
    provider = AsyncMock(return_value=provider_result)
    monkeypatch.setattr(
        "app.brain.cognition.BrainProviderAdapter.generate_structured",
        provider,
    )
    forbidden_tool_call = AsyncMock(side_effect=AssertionError("Brain must not resolve or invoke Agency tools"))
    monkeypatch.setattr("app.agentic.registry.spec", forbidden_tool_call)
    before = packet.model_dump(mode="json")

    result, trace = await run_brain_step(packet)

    steps = [item["step"] for item in trace.steps]
    assert "typed_planner_bounded" in steps
    assert "bounded_simulator_evaluated" in steps
    assert "research_brain_evaluated" in steps
    assert "specialist_reasoning_evaluated" in steps
    assert "deterministic_validator_evaluated" in steps
    assert "independent_critic_evaluated" in steps
    assert result.critic_verdict in {"REVISE", "REJECT", "RESEARCH_MORE"}
    assert result.critic_notes
    assert result.workflow_proposal is None
    assert packet.model_dump(mode="json") == before
    provider.assert_awaited_once()
    forbidden_tool_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_capability_uses_bounded_semantic_roles_before_proposal() -> None:
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(owner_user_id=owner_id, surface="plan", reason="private")
    packet = CognitiveTaskPacketV2(
        owner_user_id=owner_id,
        task_class="plan",
        user_input="Draft a plan to ship the owner review.",
        identity=_identity(),
        self_capabilities=_capabilities(),
        context_manifest=ContextManifest(scope_statement="private", token_budget=500, token_used=0),
        budget=CognitiveBudget(
            max_context_tokens=500,
            max_cost_cents=100,
            deadline_seconds=30,
        ),
    )
    hydrated = HydratedCapabilityContext(
        capability_id=PLAN_FROM_CONVERSATION_SPEC.capability_id,
        scope_envelope=scope,
        manifest=packet.context_manifest,
    )

    result = await WorkerDispatcher.dispatch(
        AsyncMock(),
        owner_user_id=owner_id,
        capability=PLAN_FROM_CONVERSATION_SPEC,
        hydrated_context=hydrated,
        query=packet.user_input,
        task_id=packet.task_id,
        packet=packet,
    )

    assert result is not None
    assert result.workflow_proposal is not None
    assert "typed planner" in result.decision_summary.lower()
    assert "bounded simulator" in result.decision_summary.lower()
    assert "independent critic" in result.decision_summary.lower()
    assert "planning specialist" in result.decision_summary.lower()


@pytest.mark.asyncio
async def test_production_agency_bridge_refuses_overwide_dag_before_tool_resolution() -> None:
    proposal = WorkflowProposal(
        task_id=uuid.uuid4(),
        title="Too wide",
        rationale="Five parallel calls exceed the production width cap.",
        steps=[
            WorkflowStepProposal(
                key=f"step-{index}",
                title=f"Step {index}",
                description="Bounded step",
                tool_key="not_resolved_because_limits_run_first",
                tool_version="1",
                arguments={},
                estimated_tokens=10,
            )
            for index in range(5)
        ],
    )

    workflow, result = await submit_workflow_proposal(
        AsyncMock(),
        owner_user_id=uuid.uuid4(),
        proposal=proposal,
    )

    assert workflow is None
    assert result.ok is False
    assert any(error.code == "DAG_LIMIT" and "MAX_WIDTH" in error.message for error in result.errors)


def test_dispatch_runtime_limits_fail_closed_for_all_dimensions() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    snapshot = {
        "workflow_state": "CANCELLED",
        "step_state": "READY",
        "created_at": now - dt.timedelta(seconds=10),
        "expires_at": now - dt.timedelta(seconds=1),
        "cost_cents": 11,
        "limits": DAGExecutionLimits(
            max_width=1,
            max_calls=1,
            max_tokens=5,
            max_cost_cents=10,
            deadline_seconds=1,
        ).model_dump(),
        "nodes": [
            {"key": "a", "depends_on": [], "estimated_tokens": 4, "estimated_cost_cents": 6},
            {"key": "b", "depends_on": [], "estimated_tokens": 4, "estimated_cost_cents": 6},
        ],
    }

    result = validate_dispatch_snapshot(snapshot, now=now)

    assert result.allowed is False
    assert {"MAX_WIDTH", "MAX_CALLS", "MAX_TOKENS", "MAX_COST", "DEADLINE", "CANCELLED"} <= set(
        result.violations
    )


@pytest.mark.asyncio
async def test_dispatcher_never_publishes_a_rejected_snapshot(monkeypatch) -> None:
    intent = DispatchIntent(
        id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        dispatch_key="dispatch-1",
        attempts=1,
        traceparent=None,
        claim_token=uuid.uuid4(),
    )
    monkeypatch.setattr("app.agentic.dispatcher.claim_intents", AsyncMock(return_value=[intent]))
    monkeypatch.setattr(
        "app.agentic.dispatcher.load_dispatch_snapshot",
        AsyncMock(
            return_value={
                "workflow_state": "CANCELLED",
                "step_state": "CANCELLED",
                "created_at": dt.datetime.now(dt.timezone.utc),
                "expires_at": None,
                "cost_cents": 0,
                "limits": DAGExecutionLimits().model_dump(),
                "nodes": [{"key": "a", "depends_on": []}],
            }
        ),
    )
    cancel = AsyncMock(return_value=True)
    monkeypatch.setattr("app.agentic.dispatcher.mark_cancelled", cancel)
    publish = AsyncMock()
    db = AsyncMock()

    result = await dispatch_once(db, dispatcher_id="test", publish=publish)

    publish.assert_not_awaited()
    cancel.assert_awaited_once()
    assert result["cancelled"] == [str(intent.id)]


def test_evaluation_gate_requires_observed_held_out_and_shadow_cases() -> None:
    corpus = EvaluationCorpus(
        version="empirical-v1",
        cases=[
            EvaluationCase(case_id="held", split="held_out", expected="PASS"),
            EvaluationCase(case_id="shadow", split="shadow", expected="PASS"),
        ],
    )
    gate = EvaluationGate.from_corpus(corpus, shadow_pass_rate=1.0)

    assert gate.can_promote({"held": "PASS"}) is False
    assert gate.can_promote({"held": "PASS", "shadow": "ERROR"}) is False
    assert gate.can_promote({"held": "PASS", "shadow": "PASS"}) is True

    incomplete_report = EvaluationRunner(
        EvaluationCorpus(
            version="empirical-v1",
            cases=[EvaluationCase(case_id="held", split="held_out", expected="PASS")],
        )
    ).run(lambda case: "PASS")
    decision = gate.evaluate(incomplete_report)
    assert decision.promote is False
    assert "missing empirical shadow observations" in decision.reason
