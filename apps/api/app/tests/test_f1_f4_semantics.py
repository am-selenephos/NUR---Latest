from __future__ import annotations

from uuid import uuid4

import pytest

from app.agentic.limits import DAGExecutionLimits, validate_dag_limits
from app.brain.schemas import ContextManifest, ScopeEnvelope, WorkflowProposalV2
from app.mind.capabilities.dispatcher import WorkerDispatcher
from app.mind.capabilities.hydrator import ContextHydrator, HydratedCapabilityContext
from app.mind.capabilities.schemas import CapabilitySpec, ContextHydrationRecipe, ExecutionMode


def test_semantic_hydration_is_owner_scoped_and_excludes_unapproved_memory() -> None:
    owner = uuid4()
    scope = ScopeEnvelope(owner_user_id=owner, surface="talk")
    hydrated = ContextHydrator.hydrate_semantic_sources(
        scope,
        approved_memory=[{"id": "m1", "owner_user_id": str(owner), "status": "APPROVED", "content": "keep"}],
        memory_candidates=[{"id": "mc1", "owner_user_id": str(owner), "status": "PENDING", "content": "never include"}],
        beliefs=[{"id": "b1", "owner_user_id": str(owner), "claim": "owner claim"}],
        user_model_claims=[{"id": "u1", "owner_user_id": str(owner), "claim": "owner model"}],
        research_results=[{"id": "r1", "owner_user_id": str(owner), "citation": "https://a.test"}],
        semantic_context=[{"id": "s1", "owner_user_id": str(owner), "kind": "workspace"}],
        token_budget=1000,
    )

    assert hydrated.approved_memory[0]["id"] == "m1"
    assert hydrated.memory_candidates == []
    assert hydrated.beliefs[0]["id"] == "b1"
    assert hydrated.user_model_claims[0]["id"] == "u1"
    assert hydrated.research_results[0]["id"] == "r1"
    assert hydrated.semantic_context[0]["id"] == "s1"
    assert any(source.kind == "approved_memory" for source in hydrated.manifest.included)
    assert any(source.kind == "memory_candidates" for source in hydrated.manifest.excluded)


def test_dag_limits_fail_closed_for_width_calls_tokens_cost_deadline_and_cancellation() -> None:
    limits = DAGExecutionLimits(
        max_width=1,
        max_calls=2,
        max_tokens=20,
        max_cost_cents=10,
        deadline_seconds=5,
    )
    result = validate_dag_limits(
        [
            {"key": "a", "depends_on": [], "estimated_tokens": 12, "estimated_cost_cents": 6},
            {"key": "b", "depends_on": [], "estimated_tokens": 12, "estimated_cost_cents": 6},
            {"key": "c", "depends_on": ["a"], "estimated_tokens": 1, "estimated_cost_cents": 1},
        ],
        limits=limits,
        elapsed_seconds=6,
        cancellation_requested=True,
    )

    assert result.allowed is False
    assert {"MAX_WIDTH", "MAX_TOKENS", "MAX_COST", "DEADLINE", "CANCELLED"} <= set(result.violations)


def test_workflow_worker_returns_the_v2_proposal_on_the_single_agency_path() -> None:
    owner = uuid4()
    context = HydratedCapabilityContext(
        capability_id="capability:plan_from_conversation",
        scope_envelope=ScopeEnvelope(owner_user_id=owner, surface="talk"),
        manifest=ContextManifest(scope_statement="private"),
    )
    capability = CapabilitySpec(
        capability_id="capability:plan_from_conversation",
        name="Plan",
        description="Plan",
        intent_signatures=("plan",),
        execution_mode=ExecutionMode.WORKFLOW_PROPOSAL,
        hydration_recipe=ContextHydrationRecipe(),
    )

    result = asyncio_run(WorkerDispatcher._execute_workflow_proposal_worker(
        capability=capability,
        hydrated_context=context,
        query="draft a plan to prepare the week",
        task_id=uuid4(),
        params={"steps": ["review calendar", "choose priorities"]},
    ))
    assert isinstance(result.workflow_proposal, WorkflowProposalV2)
    assert result.workflow_proposal.contract_version == "workflow-proposal-v2"


def asyncio_run(awaitable):
    import asyncio
    return asyncio.run(awaitable)
