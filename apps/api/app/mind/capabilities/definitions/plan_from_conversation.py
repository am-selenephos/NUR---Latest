"""Plan from Conversation capability definition.

Extracts tasks, dependencies, and actionable steps from dialogue into a draft Plan for owner review.
"""
from __future__ import annotations

from app.mind.capabilities.schemas import (
    CapabilitySpec,
    ContextHydrationRecipe,
    ExecutionMode,
    HydrationFailurePolicy,
)

PLAN_FROM_CONVERSATION_SPEC = CapabilitySpec(
    capability_id="capability:plan_from_conversation",
    name="Plan from Conversation",
    description="Draft a structured Plan and proposed action steps from conversational intent for owner review.",
    intent_signatures=(
        "make a plan",
        "draft a plan",
        "create a plan",
        "plan this out",
        "break this down into steps",
        "schedule these tasks",
        "build an action plan",
        "let's plan",
    ),
    allowed_surfaces=("talk", "plan"),
    sensitivity_ceiling="NORMAL",
    execution_mode=ExecutionMode.WORKFLOW_PROPOSAL,
    required_tools=("create_draft_plan", "get_plan"),
    worker_role="PLANNER",
    hydration_recipe=ContextHydrationRecipe(
        source_keys=("workspace_frame", "hybrid_retrieval", "active_plans"),
        required_source_keys=(),
        optional_source_keys=("workspace_frame", "hybrid_retrieval", "active_plans"),
        failure_policy=HydrationFailurePolicy.FAIL_REQUIRED_DEGRADE_OPTIONAL,
        include_workspace_frame=True,
        hybrid_retrieval_limit=6,
        fetch_active_plans=True,
        max_total_tokens=4000,
        max_context_tokens=4000,
    ),
    min_confidence_threshold=0.82,
    timeout_seconds=30,
    estimated_cost_cents=1.5,
    abstention_prompt="I notice you may want a plan, but I need more details before drafting one.",
    enabled=True,
)
