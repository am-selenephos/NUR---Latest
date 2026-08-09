"""Contextual Answer capability definition.

Direct conversational cognitive synthesis using scoped context and memory.
"""
from __future__ import annotations

from app.mind.capabilities.schemas import (
    CapabilitySpec,
    ContextHydrationRecipe,
    ExecutionMode,
    HydrationFailurePolicy,
)

CONTEXTUAL_ANSWER_SPEC = CapabilitySpec(
    capability_id="capability:contextual_answer",
    version="1",
    name="Contextual Answer",
    description="Synthesize direct answers using scoped context and memory without side effects.",
    intent_signatures=(
        "explain",
        "what is",
        "how do I",
        "why did",
        "tell me about",
        "answer my question",
        "summarize what we discussed",
        "what does this mean",
        "samjhao",
        "samjha do",
        "سمجھاؤ",
        "समझाओ",
    ),
    allowed_surfaces=("talk", "research", "reflection"),
    sensitivity_ceiling="HIGH",
    execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
    required_tools=(),
    worker_role="SYNTHESIZER",
    hydration_recipe=ContextHydrationRecipe(
        source_keys=("workspace_frame", "hybrid_retrieval"),
        required_source_keys=(),
        optional_source_keys=("workspace_frame", "hybrid_retrieval"),
        failure_policy=HydrationFailurePolicy.FAIL_REQUIRED_DEGRADE_OPTIONAL,
        include_workspace_frame=True,
        hybrid_retrieval_limit=6,
        max_total_tokens=4000,
        max_context_tokens=4000,
    ),
    min_confidence_threshold=0.82,
    timeout_seconds=30,
    estimated_cost_cents=0,
    abstention_prompt="I will provide a direct conversational response based on available context.",
    enabled=True,
)
